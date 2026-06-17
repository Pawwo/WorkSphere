from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.config import get_settings
from app.storage.db import Database
from app.storage.job_repository import JobRepository, job_url_lookup_variants
from app.services.inbox_service import InboxService
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
    if body.preset_id and body.preset_id != "custom":
        cfg = current_llm_config()
        match = next((p for p in cfg["presets"] if p["id"] == body.preset_id), None)
        if not match:
            raise HTTPException(status_code=400, detail=f"Unknown preset: {body.preset_id}")
        base_url = match["base_url"]
        if model is None and match.get("default_model"):
            model = match["default_model"]
    if not any([base_url, model, body.api_key and body.api_key.strip(), body.preset_id]):
        raise HTTPException(
            status_code=400,
            detail="Provide preset_id, base_url, model, or api_key",
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
    health = await test_llm_connection()
    cfg = current_llm_config()
    return {"config": cfg, "health": health, "message": message}


@router.get("/fit/compare")
async def compare_fit(url: str = Query(..., min_length=8)):
    """Compare quick_fit (seen_jobs), triage row, and evaluate_fit (applications DB) for a URL."""
    settings = get_settings()
    repo = JobRepository(settings.seen_jobs_path)
    seen = repo.all()

    resolved = None
    for u in job_url_lookup_variants(url):
        found = repo.get_by_url(u)
        if found:
            resolved = found
            break
    key, job = resolved if resolved else (url, None)

    inbox = InboxService(settings=settings)
    triage = inbox._load_triage_data() or {}
    ranked = triage.get("ranked") or []
    triage_row = inbox._find_ranked_item(ranked, url) if ranked else None

    app_row = await Database(settings.db_path).get_application_by_url(url)
    # Try canonical url from job entry too.
    if app_row is None and job and job.url:
        app_row = await Database(settings.db_path).get_application_by_url(job.url)

    return {
        "url": url,
        "resolved_key": key,
        "seen_job": job.model_dump() if job else None,
        "triage_row": triage_row,
        "application": app_row,
    }


async def _with_health(cfg: dict) -> dict:
    health = await test_llm_connection()
    return {**cfg, "health": health}
