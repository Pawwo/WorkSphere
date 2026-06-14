from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from app.models.setup import (
    CVImportRequest,
    CVImportResponse,
    SetupFinalizeResponse,
    SetupStatus,
    WizardSectionRequest,
    WizardState,
)
from app.services.profile_service import ProfileService
from app.services.setup_service import SetupService

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatus)
async def setup_status():
    return SetupStatus(**ProfileService().get_status())


@router.get("/wizard")
async def wizard_schema():
    return SetupService().get_wizard_schema()


@router.get("/state", response_model=WizardState)
async def wizard_state():
    return ProfileService().load_wizard_state()


@router.post("/wizard/section", response_model=WizardState)
async def save_wizard_section(body: WizardSectionRequest):
    try:
        return ProfileService().save_section(body.section, body.data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cv", response_model=CVImportResponse)
async def import_cv(body: CVImportRequest):
    if len(body.cv_text.strip()) < 50:
        raise HTTPException(status_code=400, detail="CV tekst za krótki (min. 50 znaków)")
    return await SetupService().import_cv(body.cv_text)


@router.post("/regenerate-search-queries")
async def regenerate_search_queries():
    written = ProfileService().regenerate_search_queries_file()
    return {"success": True, "files": written}


@router.post("/finalize", response_model=SetupFinalizeResponse)
async def finalize_setup():
    try:
        result = await SetupService().finalize()
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Nieprawidłowe dane w wizard_state.json: {exc.errors()[0]['msg']}",
        ) from exc
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result
