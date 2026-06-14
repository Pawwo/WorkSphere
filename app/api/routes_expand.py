from __future__ import annotations

from fastapi import APIRouter

from app.models.workflow import ExpandApplyRequest, ExpandApplyResponse, ExpandPreviewRequest, ExpandPreviewResponse
from app.services.expand_service import ExpandService

router = APIRouter(prefix="/api/expand", tags=["expand"])


@router.post("/preview", response_model=ExpandPreviewResponse)
async def expand_preview(request: ExpandPreviewRequest = ExpandPreviewRequest()):
    return await ExpandService().preview(request)


@router.post("/apply", response_model=ExpandApplyResponse)
async def expand_apply(request: ExpandApplyRequest):
    preview = None
    if request.apply_all:
        preview_resp = await ExpandService().preview(
            ExpandPreviewRequest(
                include_github=request.include_github,
                include_documents=request.include_documents,
            )
        )
        preview = preview_resp.new_competencies
    return ExpandService().apply(request, preview_items=preview)
