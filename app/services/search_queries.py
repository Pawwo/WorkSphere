"""Parse data/profile/search-queries.md (same format as upstream job-scraper skill)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from app.config import Settings, get_settings


def _normalize_query_line(line: str) -> str:
    s = line.strip()
    m = re.match(r'^"([^"]+)"\s*(.*)$', s)
    if m:
        rest = m.group(2).strip()
        return f'"{m.group(1)}"{f" {rest}" if rest else ""}'
    return s.strip('"')


def parse_search_queries(path: Optional[Path] = None) -> dict:
    settings = get_settings()
    path = path or (settings.profile_dir / "search-queries.md")
    if not path.exists():
        return {"categories": [], "primary_portals": [], "broad_portals": [], "linkedin_queries": []}

    text = path.read_text(encoding="utf-8")
    categories: List[dict] = []
    current_name = ""
    in_code = False
    queries: List[str] = []

    for line in text.splitlines():
        if line.startswith("### Priority"):
            if current_name and queries:
                categories.append({"name": current_name, "queries": queries})
            current_name = line.replace("### ", "").strip()
            queries = []
            in_code = False
            continue
        if line.strip() == "```":
            in_code = not in_code
            continue
        if in_code and line.strip():
            q = _normalize_query_line(line)
            if q:
                queries.append(q)
    if current_name and queries:
        categories.append({"name": current_name, "queries": queries})

    primary: List[str] = []
    broad: List[str] = []
    if "**Primary**" in text:
        block = text.split("**Primary**", 1)[1].split("**Broad**", 1)[0]
        primary = re.findall(r"\b(pracuj|justjoin|nofluffjobs|theprotocol|praca[_-]pl|rocketjobs)\b", block, re.I)
        primary = [p.lower().replace("-", "_").replace("praca_pl", "praca-pl") for p in primary]
    if "**Broad**" in text:
        block = text.split("**Broad**", 1)[1].split("##", 1)[0]
        broad = re.findall(r"\b(indeed|linkedin)\b", block, re.I)
        broad = [f"{b}-pl" if b in ("indeed", "linkedin") else b for b in broad]

    linkedin_queries: List[str] = []
    if "## LinkedIn Queries" in text:
        block = text.split("## LinkedIn Queries", 1)[1].split("##", 1)[0]
        in_code = False
        for line in block.splitlines():
            if line.strip() == "```":
                in_code = not in_code
                continue
            if in_code and line.strip():
                q = _normalize_query_line(line)
                if q:
                    linkedin_queries.append(q)

    return {
        "categories": categories,
        "primary_portals": primary or ["pracuj", "justjoin", "nofluffjobs", "theprotocol", "praca-pl", "rocketjobs"],
        "broad_portals": broad or ["linkedin-pl"],
        "linkedin_queries": linkedin_queries,
    }


def append_city_to_query(query: str, city: str) -> str:
    """Add city only when the query is not already location-specific."""
    if not city or not query.strip():
        return query
    low = query.lower()
    city_low = city.lower()
    if city_low in low:
        return query
    if "remote polska" in low or low.rstrip().endswith("polska"):
        return query
    if " remote" in low:
        return query
    return f"{query} {city}"


def resolve_scrape_queries(
    *,
    broad: bool = False,
    focus: Optional[str] = None,
    max_categories: int = 3,
) -> List[str]:
    parsed = parse_search_queries()
    cats = parsed["categories"]
    if not cats:
        return []

    if focus:
        focus_l = focus.lower()
        matched = [c for c in cats if focus_l in c["name"].lower()]
        pool = matched if matched else cats
    elif broad:
        pool = cats
    else:
        pool = cats[:max_categories]

    seen: set[str] = set()
    out: List[str] = []
    for cat in pool:
        for q in cat["queries"]:
            key = q.lower()
            if key not in seen:
                seen.add(key)
                out.append(q)
    return out


def resolve_linkedin_queries() -> List[str]:
    parsed = parse_search_queries()
    queries = parsed.get("linkedin_queries") or []
    if queries:
        return queries
    return [
        "COO operations Poland",
        "Head of Operations remote Poland",
        "Odoo ERP manager Poland",
        "AI transformation director Poland",
        "Program Manager operations Poland",
    ]
