"""Read/write LLM endpoint selection for /tools."""

from __future__ import annotations

from app.config import Settings, get_settings, update_yaml_llm_settings
from app.llm.client import BielikClient

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
LOCAL_LLM_BASE_URL = "http://127.0.0.1:8006/v1"


def llm_presets(settings: Settings | None = None) -> list[dict[str, str]]:
    return [
        {
            "id": "local",
            "label": "Lokalny serwer (127.0.0.1:8006)",
            "base_url": LOCAL_LLM_BASE_URL,
        },
        {
            "id": "openrouter",
            "label": "OpenRouter",
            "base_url": OPENROUTER_BASE_URL,
            "default_model": OPENROUTER_DEFAULT_MODEL,
        },
    ]


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
    return {
        "base_url": current,
        "model": s.llm_model,
        "model_file": s.llm_model_file,
        "preset_id": preset_id,
        "presets": presets,
        "is_custom": preset_id is None,
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
    update_yaml_llm_settings(
        base_url=updates.get("base_url"),
        model=updates.get("model"),
        api_key=updates.get("api_key"),
    )
    return current_llm_config()


def apply_llm_base_url(base_url: str) -> dict:
    return apply_llm_settings(base_url=base_url)


def llm_test_message(settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return f"Testuję połączenie z {s.llm_base_url}…"


async def test_llm_connection(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    client = BielikClient(s)
    return await client.healthcheck_extended(force_probe=True)
