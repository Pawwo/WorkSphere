from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.workflow import UpskillRequest, UpskillResponse
from app.services.upskill_service import UpskillService

router = APIRouter(prefix="/api/upskill", tags=["upskill"])


@router.post("", response_model=UpskillResponse)
async def run_upskill(request: UpskillRequest):
    if request.mode == "targeted" and not request.url and not request.text:
        raise HTTPException(status_code=400, detail="Tryb targeted wymaga url lub text")
    try:
        return await UpskillService().run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
