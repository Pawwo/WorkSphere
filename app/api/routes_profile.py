from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.profile_service import PROFILE_FILES, ProfileService

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("")
async def list_profile_files():
    svc = ProfileService()
    status = svc.get_status()
    return {"files": PROFILE_FILES, "status": status}


@router.get("/{filename}")
async def get_profile_file(filename: str):
    if filename not in PROFILE_FILES:
        raise HTTPException(status_code=404, detail="Nieznany plik profilu")
    try:
        content = ProfileService().read_file(filename)
        return {"filename": filename, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Plik nie istnieje") from None
