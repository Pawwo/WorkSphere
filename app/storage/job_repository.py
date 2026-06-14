"""Unified access to seen_jobs.json with incremental updates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Optional
from urllib.parse import unquote

from app.models.jobs import SeenJobEntry


def job_url_lookup_variants(url: str) -> list[str]:
    """URLs that should resolve to the same seen_jobs entry (LinkedIn % vs %25 slugs)."""
    variants = {url, unquote(url)}
    if "%" in url:
        variants.add(url.replace("%", "%25"))
    if "%25" in url:
        variants.add(url.replace("%25", "%"))
    return list(variants)


class JobRepository:
    def __init__(self, path: Path):
        self.path = path
        self._cache: Dict[str, SeenJobEntry] | None = None
        self._dirty = False

    def _ensure_loaded(self) -> Dict[str, SeenJobEntry]:
        if self._cache is None:
            if not self.path.exists():
                self._cache = {}
            else:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                seen = data.get("seen", {})
                self._cache = {k: SeenJobEntry(**v) for k, v in seen.items()}
        return self._cache

    def all(self) -> Dict[str, SeenJobEntry]:
        return dict(self._ensure_loaded())

    def get_by_url(self, url: str) -> tuple[str, SeenJobEntry] | None:
        seen = self._ensure_loaded()
        for candidate in job_url_lookup_variants(url):
            for key, job in seen.items():
                if job.url == candidate or key == candidate:
                    return key, job
        return None

    def upsert(self, key: str, job: SeenJobEntry) -> None:
        self._ensure_loaded()[key] = job
        self._dirty = True

    def update_fields(self, url: str, **fields) -> bool:
        found = self.get_by_url(url)
        if not found:
            return False
        key, job = found
        data = job.model_dump()
        data.update({k: v for k, v in fields.items() if v is not None})
        self._ensure_loaded()[key] = SeenJobEntry(**data)
        self._dirty = True
        return True

    def upsert_many(self, entries: Iterable[tuple[str, SeenJobEntry]]) -> int:
        seen = self._ensure_loaded()
        count = 0
        for key, job in entries:
            if key not in seen:
                count += 1
            seen[key] = job
            self._dirty = True
        return count

    def flush(self) -> None:
        if not self._dirty or self._cache is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"seen": {k: v.model_dump() for k, v in self._cache.items()}}
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._dirty = False

    def invalidate(self) -> None:
        self._cache = None
        self._dirty = False

    @classmethod
    def from_settings(cls, settings=None) -> JobRepository:
        from app.config import get_settings

        s = settings or get_settings()
        return cls(s.seen_jobs_path)
