from __future__ import annotations

from pathlib import Path
from typing import List, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings

router = APIRouter(prefix="/api/documents", tags=["documents"])

ALLOWED_CATEGORIES = {"cv", "linkedin", "diplomas", "references", "applications"}
MAX_SIZE = 10 * 1024 * 1024


@router.get("")
async def list_documents():
    settings = get_settings()
    base = settings.data_dir / "documents"
    result: dict[str, List[str]] = {}
    if not base.exists():
        return {"categories": result}
    for cat in ALLOWED_CATEGORIES:
        cat_dir = base / cat
        if cat_dir.exists():
            result[cat] = [p.name for p in sorted(cat_dir.iterdir()) if p.is_file()]
        else:
            result[cat] = []
    return {"categories": result}


@router.post("/upload")
async def upload_document(
    category: Literal["cv", "linkedin", "diplomas", "references", "applications"] = Form(...),
    file: UploadFile = File(...),
):
    if category not in ALLOWED_CATEGORIES:
        raise HTTPException(status_code=400, detail="Nieprawidłowa kategoria")

    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Plik za duży (max 10 MB)")
    if not content:
        raise HTTPException(status_code=400, detail="Pusty plik")

    settings = get_settings()
    dest_dir = settings.data_dir / "documents" / category
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or "upload.bin").name
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Nieprawidłowa nazwa pliku")

    dest = dest_dir / filename
    dest.write_bytes(content)

    return {
        "saved": str(dest.relative_to(settings.repo_root)),
        "category": category,
        "filename": filename,
        "size": len(content),
    }
