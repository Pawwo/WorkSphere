"""Job posting freshness checks (48h default)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def is_fresh(
    date_str: str | None,
    *,
    max_age_hours: int,
    strict: bool = True,
) -> bool:
    if not date_str or not str(date_str).strip():
        return not strict
    try:
        raw = str(date_str).strip()
        if len(raw) == 10 and raw[4] == "-":
            dt = datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        return dt >= cutoff
    except (ValueError, TypeError):
        return not strict


def effective_days(max_age_hours: int, configured_days: int) -> int:
    """API pre-filter days — at least 1, at most configured_days."""
    from_days = max(1, (max_age_hours + 23) // 24)
    if configured_days <= 0:
        return from_days
    return min(configured_days, from_days)


def portal_strict_freshness(
    portal: str,
    *,
    global_strict: bool,
    portal_overrides: dict[str, bool],
) -> bool:
    normalized = portal.replace("_", "-")
    for key in (portal, normalized, portal.replace("-", "_")):
        if key in portal_overrides:
            return portal_overrides[key]
    return global_strict
