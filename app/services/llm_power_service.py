from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.config import Settings, get_settings
from app.services.llm_settings_service import is_local_bielik_endpoint

logger = logging.getLogger(__name__)


class LlmPowerService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.llm_wake_enabled
            and self.settings.llm_wake_url
            and is_local_bielik_endpoint(self.settings)
        )

    async def get_status(self) -> dict:
        if not self.settings.llm_wake_url:
            return {"llm": "unknown"}
        url = f"{self.settings.llm_wake_url.rstrip('/')}/status"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.debug("LLM power status unavailable: %s", exc)
            return {"llm": "unknown", "error": str(exc)}

    async def wake(self) -> bool:
        if not self.enabled:
            return True
        url = f"{self.settings.llm_wake_url.rstrip('/')}/wake"
        timeout = max(30.0, float(self.settings.llm_wake_timeout_seconds))
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url)
                data = resp.json() if resp.content else {}
                if resp.status_code == 200 and data.get("ok"):
                    return True
                logger.warning("LLM wake failed: %s %s", resp.status_code, data)
        except Exception as exc:
            logger.warning("LLM wake error: %s", exc)
        return False

    async def wake_and_prepare(self) -> dict:
        """Wake BC-250 manager then wait until Bielik passes models + probe."""
        from app.llm.client import BielikClient, clear_probe_cache

        clear_probe_cache()
        if self.enabled:
            woke = await self.wake()
            if not woke:
                st = await self.get_status()
                return {
                    "ok": False,
                    "wake_ok": False,
                    "status": st.get("llm", "unknown"),
                    "error": st.get("error") or "wake failed — sprawdź BC-250 i :8099",
                }
        client = BielikClient(self.settings)
        return await client.wait_until_ready(
            timeout=float(self.settings.llm_wake_timeout_seconds),
            probe=True,
            force_probe=True,
        )
