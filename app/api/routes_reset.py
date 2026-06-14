from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.workflow import (
    ResetExecuteRequest,
    ResetExecuteResponse,
    ResetPreviewRequest,
    ResetPreviewResponse,
)
from app.services.reset_service import ResetService

router = APIRouter(prefix="/api/reset", tags=["reset"])


@router.post("/preview", response_model=ResetPreviewResponse)
async def reset_preview(request: ResetPreviewRequest):
    return ResetService().preview(request)


@router.post("", response_model=ResetExecuteResponse)
async def reset_execute(request: ResetExecuteRequest):
    result = ResetService().execute(request)
    if "anulowany" in result.message:
        raise HTTPException(status_code=400, detail=result.message)
    return result
