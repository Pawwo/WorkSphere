from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Set, Tuple

from app.config import Settings, get_settings
from app.models.jobs import SeenJobEntry
from app.storage.job_repository import JobRepository


def load_seen_jobs(path: Path) -> Dict[str, SeenJobEntry]:
    """Deprecated: prefer JobRepository.all()."""
    return JobRepository(path).all()


def save_seen_jobs(path: Path, seen: Dict[str, SeenJobEntry]) -> None:
    """Deprecated: prefer JobRepository upsert + flush."""
    repo = JobRepository(path)
    for key, job in seen.items():
        repo.upsert(key, job)
    repo.flush()


def seen_key(url: str, company: str, title: str) -> str:
    if url:
        return url
    return f"{(company or '').strip().lower()}|{(title or '').strip().lower()}"


def is_http_url(url: str | None) -> bool:
    if not url:
        return False
    return url.strip().lower().startswith(("http://", "https://"))


def job_public_url(url: str | None) -> str:
    u = (url or "").strip()
    return u if is_http_url(u) else ""


def load_tracker_keys(path: Path) -> Set[Tuple[str, str]]:
    keys: Set[Tuple[str, str]] = set()
    if not path.exists():
        return keys
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = (row.get("company") or "").strip().lower()
            role = (row.get("role") or "").strip().lower()
            if company and role:
                keys.add((company, role))
    return keys


def read_profile_excerpt(settings: Settings | None = None, max_chars: int = 3000) -> str:
    settings = settings or get_settings()
    profile_file = settings.profile_dir / "01-candidate-profile.md"
    if profile_file.exists():
        return profile_file.read_text(encoding="utf-8")[:max_chars]
    claude = settings.profile_dir / "CLAUDE.md"
    if claude.exists():
        return claude.read_text(encoding="utf-8")[:max_chars]
    return "Brak profilu — uruchom setup."


def today_iso() -> str:
    return date.today().isoformat()


TRACKER_COLUMNS = [
    "date",
    "company",
    "role",
    "url",
    "status",
    "fit_score",
    "notes",
    "cv_file",
    "cover_file",
]


def append_tracker_row(
    path: Path,
    *,
    company: str,
    role: str,
    url: str = "",
    status: str = "applied",
    fit_score: str = "",
    notes: str = "",
    cv_file: str = "",
    cover_file: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "date": today_iso(),
        "company": company,
        "role": role,
        "url": url,
        "status": status,
        "fit_score": fit_score,
        "notes": notes,
        "cv_file": cv_file,
        "cover_file": cover_file,
    }
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def read_tracker_rows(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))
