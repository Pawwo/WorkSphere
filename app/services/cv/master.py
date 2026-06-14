"""Master CV source file access."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.config import Settings, get_settings


def master_cv_path(settings: Settings) -> Path:
    cv_dir = settings.data_dir / "documents" / "CV"
    for name in (
        "PAWEŁ WODYŃSKI — MASTER CV SOURCE.txt",
        "PAWEŁ WODYŃSKI - MASTER CV SOURCE.txt",
    ):
        p = cv_dir / name
        if p.exists():
            return p
    return cv_dir / "PAWEŁ WODYŃSKI — MASTER CV SOURCE.txt"


def resolve_master_cv_text(settings: Optional[Settings] = None) -> str:
    """Master CV text: file on disk, then wizard cv_text."""
    settings = settings or get_settings()
    path = master_cv_path(settings)
    if path.exists():
        return path.read_text(encoding="utf-8")
    from app.services.profile_service import ProfileService

    state = ProfileService(settings).load_wizard_state()
    return (state.cv_text or "").strip()


def _extract_summary_block(text: str, *, prefer_polish: bool = False) -> str:
    patterns = (
        [
            r"STRESZCZENIE EXECUTIVE\s*\n(.*?)(?:\nKLUCZOWE KOMPETENCJE|\nSUMMARY ATS|\n[A-ZĄĆĘŁŃÓŚŹŻ]{4,})",
            r"SUMMARY ATS\s*\n(.*?)(?:\nKLUCZOWE KOMPETENCJE|\n[A-ZĄĆĘŁŃÓŚŹŻ]{4,})",
        ]
        if prefer_polish
        else [
            r"SUMMARY ATS\s*\n(.*?)(?:\nKLUCZOWE KOMPETENCJE|\n[A-ZĄĆĘŁŃÓŚŹŻ]{4,})",
            r"STRESZCZENIE EXECUTIVE\s*\n(.*?)(?:\nKLUCZOWE KOMPETENCJE|\nSUMMARY ATS|\n[A-ZĄĆĘŁŃÓŚŹŻ]{4,})",
        ]
    )
    for pattern in patterns:
        m = re.search(pattern, text, re.S)
        if m:
            return re.sub(r"\n{3,}", "\n\n", m.group(1).strip())
    return ""


def load_master_ats_summary(
    settings: Optional[Settings] = None,
    *,
    language: str = "en",
) -> str:
    settings = settings or get_settings()
    text = resolve_master_cv_text(settings)
    if not text:
        return ""
    prefer_polish = (language or "en").strip().lower().startswith("pl")
    return _extract_summary_block(text, prefer_polish=prefer_polish)


def load_master_excerpt(max_chars: int = 6000, settings: Optional[Settings] = None) -> str:
    settings = settings or get_settings()
    text = resolve_master_cv_text(settings)
    if not text:
        return ""
    return text[:max_chars]
