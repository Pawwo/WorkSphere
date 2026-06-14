from __future__ import annotations

from fastapi import APIRouter

from app.services.application_service import ApplicationService

router = APIRouter(prefix="/api/tracker", tags=["tracker"])


@router.get("")
async def list_tracker():
    """Legacy tracker endpoint — backed by SQLite applications."""
    rows = await ApplicationService().list(limit=500)
    legacy = [
        {
            "date": (r.get("updated_at") or r.get("created_at") or "")[:10],
            "company": r.get("company"),
            "role": r.get("role"),
            "status": r.get("hiring_stage"),
            "fit_score": r.get("overall_fit"),
            "cv_file": r.get("cv_file"),
            "cover_file": r.get("cover_file"),
            "url": r.get("url"),
            "application_id": r.get("id"),
        }
        for r in rows
    ]
    return {"total": len(legacy), "rows": legacy}
