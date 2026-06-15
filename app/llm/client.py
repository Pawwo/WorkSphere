from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from app.config import Settings, get_settings
from app.llm.exceptions import LlmDegradedError
from app.llm.structured import extract_json
from app.llm.token_budgets import QUICK_FIT
from app.prompts.loader import render_prompt
from app.services.apply_prompt_utils import safe_max_tokens

logger = logging.getLogger(__name__)

_llm_semaphore: asyncio.Semaphore | None = None
_llm_semaphore_limit: int = 0
_http_client: httpx.AsyncClient | None = None
_probe_cache: dict[str, Any] = {"ts": 0.0, "ok": None, "esc_detected": False}

QUICK_FIT_PROFILE_MAX = 1200
QUICK_FIT_DESCRIPTION_MAX = 800
ESC_GUARD_MIN_OUTPUT = 64


def _get_llm_semaphore(settings: Settings) -> asyncio.Semaphore:
    global _llm_semaphore, _llm_semaphore_limit
    limit = max(1, getattr(settings, "llm_concurrency", 2))
    if _llm_semaphore is None or _llm_semaphore_limit != limit:
        _llm_semaphore = asyncio.Semaphore(limit)
        _llm_semaphore_limit = limit
    return _llm_semaphore


def _get_http_client(settings: Settings) -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=settings.llm_timeout_seconds)
    return _http_client


def clear_probe_cache() -> None:
    _probe_cache["ts"] = 0.0
    _probe_cache["ok"] = None
    _probe_cache["esc_detected"] = False
    _probe_cache.pop("last_esc", None)


def _response_degraded(text: str, *, check_json: bool) -> bool:
    if text.count("\x1b") > 0:
        return True
    if not check_json:
        return False
    parsed = extract_json(text)
    return not isinstance(parsed, (dict, list))


class BielikClient:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.base_url = self.settings.llm_base_url.rstrip("/")
        self._resolved_model: Optional[str] = None

    @property
    def model(self) -> str:
        return self._resolved_model or self.settings.llm_model

    async def _fetch_model_ids(self) -> List[str]:
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            )
            response.raise_for_status()
            data = response.json()
            ids: List[str] = []
            for item in data.get("data", []):
                mid = item.get("id") or item.get("name")
                if mid:
                    ids.append(mid)
            for item in data.get("models", []):
                mid = item.get("model") or item.get("name")
                if mid and mid not in ids:
                    ids.append(mid)
            return ids

    async def resolve_model(self) -> str:
        if self._resolved_model:
            return self._resolved_model
        configured = self.settings.llm_model
        try:
            available = await self._fetch_model_ids()
            if configured in available:
                self._resolved_model = configured
            elif available:
                gguf = [m for m in available if configured.split(".")[0] in m]
                self._resolved_model = gguf[0] if gguf else available[0]
                if self._resolved_model != configured:
                    logger.info("LLM model resolved: %s -> %s", configured, self._resolved_model)
            else:
                self._resolved_model = configured
        except Exception as exc:
            logger.warning("Could not resolve LLM model: %s", exc)
            self._resolved_model = configured
        return self._resolved_model

    async def healthcheck(self) -> dict:
        last_error = ""
        for attempt in range(3):
            try:
                available = await self._fetch_model_ids()
                model = await self.resolve_model()
                ok = bool(available)
                if ok and model not in available:
                    ok = any(
                        model in mid or mid in model or model.split(".")[0] in mid
                        for mid in available
                    )
                    if ok and model not in available:
                        self._resolved_model = available[0]
                if not ok and available:
                    ok = True
                    self._resolved_model = available[0]
                if ok:
                    return {
                        "ok": True,
                        "status": "ready",
                        "url": self.base_url,
                        "model": self.model,
                        "model_file": self.settings.llm_model_file,
                        "available_models": available[:5],
                    }
                last_error = "Brak modeli w /v1/models"
            except Exception as exc:
                last_error = str(exc)
                logger.warning("LLM healthcheck attempt %s failed: %s", attempt + 1, exc)
            if attempt < 2:
                await asyncio.sleep(1.0)
        result: dict = {"ok": False, "url": self.base_url, "error": last_error, "status": "error"}
        return result

    async def _cached_probe(self, *, force: bool = False) -> tuple[bool, bool]:
        """Return (inference_ok, esc_detected)."""
        if not getattr(self.settings, "llm_inference_probe_enabled", True):
            return True, False
        ttl = max(30, int(getattr(self.settings, "llm_inference_probe_cache_seconds", 90)))
        now = time.monotonic()
        if (
            not force
            and _probe_cache["ok"] is not None
            and (now - float(_probe_cache["ts"])) < ttl
        ):
            return bool(_probe_cache["ok"]), bool(_probe_cache["esc_detected"])

        ok = await self.probe_chat()
        esc = not ok and _probe_cache.get("last_esc", False)
        _probe_cache.update(ts=now, ok=ok, esc_detected=esc, last_esc=esc)
        return ok, esc

    async def healthcheck_extended(self, *, force_probe: bool = False) -> dict:
        base = await self.healthcheck()
        models_ok = bool(base.get("ok"))
        inference_ok: bool | None = None
        esc_detected = False
        if models_ok and getattr(self.settings, "llm_inference_probe_enabled", True):
            inference_ok, esc_detected = await self._cached_probe(force=force_probe)
        elif not models_ok:
            inference_ok = False
        ok = models_ok and (inference_ok is not False)
        return {
            **base,
            "ok": ok,
            "models_ok": models_ok,
            "inference_ok": inference_ok,
            "esc_detected": esc_detected,
            "status": base.get("status") if models_ok else base.get("status", "error"),
        }

    async def probe_chat(self) -> bool:
        """Verify inference quality, not just /models (detects Vulkan ESC degeneration)."""
        try:
            text = await self.chat_complete(
                [
                    {"role": "system", "content": "Zwracasz tylko JSON."},
                    {
                        "role": "user",
                        "content": 'Zwróć JSON: {"overall_fit":"moderate","recommendation":"ok"}',
                    },
                ],
                max_tokens=48,
                temperature=0.0,
                _skip_esc_guard=True,
            )
            esc = text.count("\x1b")
            _probe_cache["last_esc"] = esc > 0
            if esc > 0:
                logger.warning(
                    "LLM probe_chat: ESC degradation detected (esc=%s)",
                    esc,
                )
                return False
            parsed = extract_json(text)
            if not isinstance(parsed, dict) or parsed.get("overall_fit") not in (
                "strong",
                "moderate",
                "weak",
            ):
                logger.warning(
                    "LLM probe_chat: invalid JSON (preview=%r)",
                    (text or "")[:120],
                )
                return False
            return True
        except Exception as exc:
            logger.warning("LLM probe_chat failed: %s", exc)
            return False

    async def is_ready(self, *, probe: bool = True, force_probe: bool = False) -> bool:
        """Models endpoint OK and (optionally) a short JSON completion succeeds."""
        use_probe = probe and getattr(self.settings, "llm_inference_probe_enabled", True)
        hc = await self.healthcheck()
        if hc.get("ok"):
            if use_probe:
                inference_ok, _ = await self._cached_probe(force=force_probe)
                return inference_ok
            return True
        if use_probe:
            return await self.probe_chat()
        return False

    async def wait_until_ready(
        self,
        *,
        timeout: float | None = None,
        probe: bool = True,
        poll_interval: float = 2.0,
        force_probe: bool = False,
    ) -> dict:
        """Poll until models (+ optional probe) succeed or timeout."""
        limit = float(
            timeout
            if timeout is not None
            else max(30.0, float(getattr(self.settings, "llm_timeout_seconds", 180)))
        )
        deadline = time.monotonic() + limit
        last: dict = {"ok": False, "status": "error"}
        while time.monotonic() < deadline:
            if await self.is_ready(probe=probe, force_probe=force_probe):
                ext = await self.healthcheck_extended(force_probe=force_probe)
                return ext
            last = await self.healthcheck_extended(force_probe=force_probe)
            if last.get("status") == "idle":
                last["status"] = "starting"
            await asyncio.sleep(poll_interval)
            force_probe = True
        return {**last, "ok": False, "error": last.get("error") or "timeout waiting for LLM"}

    async def _post_completion(
        self,
        payload: Dict[str, Any],
        *,
        budgeted: int,
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        last_error = "unknown"
        client = _get_http_client(self.settings)
        for attempt, mt in enumerate([budgeted, min(budgeted, 384), min(budgeted, 192), 96]):
            payload["max_tokens"] = mt
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.settings.llm_api_key}",
                    "Content-Type": "application/json",
                },
            )
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"]
            last_error = response.text[:500]
            logger.warning(
                "LLM chat HTTP %s (attempt %s, max_tokens=%s): %s",
                response.status_code,
                attempt + 1,
                mt,
                last_error,
            )
            retryable = response.status_code in (400, 422) or (
                response.status_code == 500 and "context" in last_error.lower()
            )
            if not retryable:
                response.raise_for_status()
        raise RuntimeError(f"LLM chat failed after retries: {last_error}")

    async def chat_complete(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        _skip_esc_guard: bool = False,
    ) -> str:
        model = await self.resolve_model()
        requested = max_tokens or self.settings.llm_max_tokens
        n_ctx = getattr(self.settings, "llm_context_size", 4096)
        budgeted = safe_max_tokens(messages, requested, n_ctx=n_ctx)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": budgeted,
            "temperature": temperature if temperature is not None else self.settings.llm_temperature,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
        }
        check_json = budgeted > ESC_GUARD_MIN_OUTPUT and not _skip_esc_guard

        async with _get_llm_semaphore(self.settings):
            text = await self._post_completion(payload, budgeted=budgeted)
            if not _skip_esc_guard and _response_degraded(text, check_json=check_json):
                logger.warning(
                    "LLM degraded response (esc/json), retrying once (max_tokens=%s)",
                    budgeted,
                )
                retry_budget = min(budgeted, 384)
                payload["temperature"] = 0.0
                payload["max_tokens"] = retry_budget
                text = await self._post_completion(payload, budgeted=retry_budget)
                if _response_degraded(text, check_json=check_json):
                    raise LlmDegradedError("LLM returned ESC garbage or invalid JSON after retry")
            return text

    async def quick_fit(self, profile_excerpt: str, job: dict) -> str:
        prompt = render_prompt(
            "quick_fit.jinja2",
            profile_excerpt=profile_excerpt[:QUICK_FIT_PROFILE_MAX],
            job={
                "title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "description": (job.get("description") or "")[:QUICK_FIT_DESCRIPTION_MAX],
            },
        )
        try:
            result = await self.chat_complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "Jesteś asystentem rekrutacyjnym. "
                            "Odpowiadasz jednym słowem: high, medium lub low."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=QUICK_FIT,
                temperature=0.0,
                _skip_esc_guard=True,
            )
            match = re.search(r"\b(high|medium|low)\b", result.strip().lower())
            if match:
                return match.group(1)
            return "medium"
        except Exception as exc:
            logger.warning("quick_fit LLM failed: %s", exc)
            return "medium"
