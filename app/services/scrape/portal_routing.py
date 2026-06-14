"""Smart portal selection per query."""

from __future__ import annotations

import re

from app.services.scrape.portals import normalize_portal

EXEC_KEYWORDS = re.compile(
    r"\b("
    r"coo|ceo|dyrektor|operations|erp|odoo|founder|zarząd|"
    r"chief|director|head\s+of|transformation|consulting|delivery"
    r")\b",
    re.I,
)
DEV_PORTALS = frozenset({"justjoin", "nofluffjobs", "rocketjobs", "theprotocol"})


def portals_for_query(
    all_portals: list[str],
    query: str,
    *,
    smart_routing: bool,
) -> list[str]:
    if not smart_routing or not EXEC_KEYWORDS.search(query):
        return list(all_portals)
    kept = [p for p in all_portals if normalize_portal(p) not in DEV_PORTALS]
    return kept or list(all_portals)
