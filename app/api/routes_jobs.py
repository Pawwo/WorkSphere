from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.models.jobs import ScrapeResultItem, SeenJobUpdate
from app.services.highlights_service import enrich_highlights_for_new_jobs
from app.services.jobs_service import JobsService
from app.storage.files import load_seen_jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    status: str | None = Query(None, pattern="^(new|skipped|evaluated)$"),
    fit: str | None = Query(None, pattern="^(high|medium|low)$"),
    new_only: bool = False,
):
    return JobsService().list_jobs(status=status, fit=fit, new_only=new_only)


@router.get("/present")
async def present_new_matches():
    """Step 5 format from job-scraper SKILL."""
    return JobsService().present_new_matches()


@router.post("/enrich-highlights")
async def enrich_highlights():
    """Backfill high-match highlights for jobs missing them."""
    settings = get_settings()
    seen = load_seen_jobs(settings.seen_jobs_path)
    items = [
        ScrapeResultItem(
            fit=j.fit,
            title=j.title,
            company=j.company,
            location=j.location,
            url=j.url,
            portal=j.portal or "",
            description="",
        )
        for j in seen.values()
        if j.fit == "high" and not j.highlights
    ]
    await enrich_highlights_for_new_jobs(items)
    return {"enriched": len(items)}


@router.patch("/{url:path}")
async def update_job(url: str, update: SeenJobUpdate):
    ok = JobsService().update_job(url, update)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True, "url": url, "update": update.model_dump(exclude_none=True)}
