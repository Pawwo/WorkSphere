"""Read/write LLM endpoint selection for /tools."""

from __future__ import annotations

from urllib.parse import urlparse

from app.config import Settings, get_settings, update_yaml_llm_settings
from app.llm.client import BielikClient

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


def _host_from_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or "127.0.0.1"


def bielik_presets(settings: Settings | None = None) -> list[dict[str, str]]:
    s = settings or get_settings()
    host = _host_from_url(s.llm_base_url)
    return [
        {
            "id": "8000",
            "label": f"Bielik :8000 ({host})",
            "base_url": f"http://{host}:8000/v1",
        },
        {
            "id": "8006",
            "label": f"Bielik :8006 ({host})",
            "base_url": f"http://{host}:8006/v1",
        },
    ]


def llm_presets(settings: Settings | None = None) -> list[dict[str, str]]:
    return [
        *bielik_presets(settings),
        {
            "id": "openrouter",
            "label": "OpenRouter",
            "base_url": OPENROUTER_BASE_URL,
            "default_model": OPENROUTER_DEFAULT_MODEL,
        },
    ]


def is_local_bielik_endpoint(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    current = s.llm_base_url.rstrip("/")
    return any(p["base_url"].rstrip("/") == current for p in bielik_presets(s))


def _api_key_meta(api_key: str) -> tuple[bool, str | None]:
    key = (api_key or "").strip()
    if not key or key == "unused":
        return False, None
    if len(key) >= 4:
        return True, f"…{key[-4:]}"
    return True, "…set"


def _resolve_preset_id(base_url: str, settings: Settings) -> str | None:
    current = base_url.rstrip("/")
    for preset in llm_presets(settings):
        if preset["base_url"].rstrip("/") == current:
            return preset["id"]
    return None


def current_llm_config(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    presets = llm_presets(s)
    current = s.llm_base_url.rstrip("/")
    preset_id = _resolve_preset_id(current, s)
    api_key_set, api_key_hint = _api_key_meta(s.llm_api_key)
    wake_active = bool(
        s.llm_wake_enabled and s.llm_wake_url and is_local_bielik_endpoint(s)
    )
    return {
        "base_url": current,
        "model": s.llm_model,
        "model_file": s.llm_model_file,
        "preset_id": preset_id,
        "presets": presets,
        "is_custom": preset_id is None,
        "is_local_bielik": is_local_bielik_endpoint(s),
        "wake_active": wake_active,
        "api_key_set": api_key_set,
        "api_key_hint": api_key_hint,
    }


def apply_llm_settings(
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> dict:
    updates: dict[str, str] = {}
    if base_url is not None:
        normalized = base_url.strip().rstrip("/")
        if not normalized.startswith("http"):
            raise ValueError("base_url must start with http:// or https://")
        updates["base_url"] = normalized
    if model is not None:
        model_value = model.strip()
        if not model_value:
            raise ValueError("model cannot be empty")
        updates["model"] = model_value
    if api_key is not None and api_key.strip():
        updates["api_key"] = api_key.strip()
    if not updates:
        raise ValueError("Provide at least one of base_url, model, api_key")
    update_yaml_llm_settings(**updates)
    return current_llm_config()


def apply_llm_base_url(base_url: str) -> dict:
    return apply_llm_settings(base_url=base_url)


def llm_test_message(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    if is_local_bielik_endpoint(s):
        return "Uruchamiam LLM na local GPU i testuję połączenie…"
    return f"Testuję połączenie z {s.llm_base_url}…"


async def test_llm_connection(settings: Settings | None = None, *, wake: bool = False) -> dict:
    s = settings or get_settings()
    wake_info: dict | None = None
    if wake:
        from app.services.llm_power_service import LlmPowerService

        power = LlmPowerService(s)
        if power.enabled:
            wake_info = await power.wake_and_prepare()
    client = BielikClient(s)
    health = await client.healthcheck_extended(force_probe=True)
    if wake_info is not None:
        health = {**health, "wake": wake_info}
    return health
