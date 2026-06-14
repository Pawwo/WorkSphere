"""Shared inbox list filtering."""

from __future__ import annotations

from app.models.jobs import FitFilter, SeenJobEntry, StatusFilter
from app.services.fit_utils import fit_sort_key


def matches_query(blob: str, q: str | None) -> bool:
    if not q:
        return True
    return q.lower() in blob.lower()


def filter_seen_jobs(
    seen: dict[str, SeenJobEntry],
    *,
    status: StatusFilter = None,
    fit: FitFilter = None,
    q: str | None = None,
    new_only: bool = False,
) -> list[tuple[str, SeenJobEntry]]:
    rows: list[tuple[str, SeenJobEntry]] = []
    for key, job in seen.items():
        if status and job.status != status:
            continue
        if fit and job.fit != fit:
            continue
        if new_only and job.status != "new":
            continue
        if not matches_query(f"{job.title} {job.company}", q):
            continue
        rows.append((key, job))
    rows.sort(key=lambda pair: (fit_sort_key(pair[1].fit), pair[1].first_seen))
    return rows


def filter_triage_item(
    item: dict,
    seen: dict[str, SeenJobEntry],
    *,
    tier: str | None,
    status: StatusFilter,
    fit: FitFilter,
    q: str | None,
    effective_tier,
    effective_status,
    queue_urls: set[str] | None = None,
) -> bool:
    url = item.get("url", "")
    if tier == "evaluate":
        if queue_urls is not None and url not in queue_urls:
            return False
    elif tier and effective_tier(item, seen) != tier:
        return False
    if status and effective_status(item, seen) != status:
        return False
    if fit and item.get("quick_fit") != fit:
        return False
    if not matches_query(f"{item.get('title', '')} {item.get('company', '')}", q):
        return False
    return True
