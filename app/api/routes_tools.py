from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.llm_settings_service import (
    apply_llm_settings,
    current_llm_config,
    llm_test_message,
    test_llm_connection,
)

router = APIRouter(prefix="/api/tools", tags=["tools"])


class LlmSettingsUpdate(BaseModel):
    base_url: str | None = None
    preset_id: str | None = None
    model: str | None = None
    api_key: str | None = None


@router.get("/llm")
async def get_llm_settings():
    return await _with_health(current_llm_config())


@router.put("/llm")
async def update_llm_settings(body: LlmSettingsUpdate):
    base_url = body.base_url
    model = body.model
    if body.preset_id:
        cfg = current_llm_config()
        match = next((p for p in cfg["presets"] if p["id"] == body.preset_id), None)
        if not match:
            raise HTTPException(status_code=400, detail=f"Unknown preset: {body.preset_id}")
        base_url = match["base_url"]
        if model is None and match.get("default_model"):
            model = match["default_model"]
    if not any([base_url, model, body.api_key and body.api_key.strip()]):
        raise HTTPException(
            status_code=400,
            detail="Provide base_url, preset_id, model, or api_key",
        )
    try:
        cfg = apply_llm_settings(
            base_url=base_url,
            model=model,
            api_key=body.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await _with_health(cfg)


@router.post("/llm/test")
async def test_llm_settings():
    message = llm_test_message()
    health = await test_llm_connection(wake=True)
    cfg = current_llm_config()
    return {"config": cfg, "health": health, "message": message}


async def _with_health(cfg: dict) -> dict:
    health = await test_llm_connection()
    return {**cfg, "health": health}
