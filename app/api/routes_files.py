from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.config import get_settings

router = APIRouter(prefix="/api/files", tags=["files"])


def _safe_path(base: Path, filename: str) -> Path:
    name = Path(filename).name
    if name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa pliku")
    path = base / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="Plik nie istnieje")
    return path


@router.get("/cv/{filename}")
async def get_cv_file(filename: str):
    settings = get_settings()
    return FileResponse(_safe_path(settings.repo_root / "cv", filename))


@router.get("/cover/{filename}")
async def get_cover_file(filename: str):
    settings = get_settings()
    return FileResponse(_safe_path(settings.repo_root / "cover_letters", filename))


@router.get("/app/{filepath:path}")
async def get_app_file(filepath: str):
    settings = get_settings()
    base = settings.repo_root.resolve()
    path = (base / filepath).resolve()
    if not str(path).startswith(str(base)) or not path.is_file():
        raise HTTPException(status_code=404, detail="Plik nie istnieje")
    return FileResponse(path)
