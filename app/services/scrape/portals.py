"""Portal tier configuration and query resolution."""

from __future__ import annotations

from typing import List

import yaml

from app.config import Settings
from app.scrapers.bun_cli import PORTAL_SKILLS
from app.services.search_queries import parse_search_queries

TIER1_PORTALS = ["pracuj", "praca-pl", "justjoin", "rocketjobs"]
TIER2_PORTALS = ["nofluffjobs", "theprotocol"]
TIER3_PORTALS = ["linkedin-pl", "indeed-pl"]


def normalize_portal(name: str) -> str:
    return name.replace("_", "-")


def load_portal_lists(settings: Settings) -> tuple[List[str], List[str]]:
    parsed = parse_search_queries()
    primary = parsed["primary_portals"]
    broad_extra = parsed["broad_portals"]
    if primary:
        return primary, broad_extra

    yaml_path = settings.repo_root / "config.yaml"
    if yaml_path.exists():
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        scrapers = raw.get("scrapers", {})
        primary = scrapers.get("portals", {}).get("primary", [])
        broad_extra = scrapers.get("portals", {}).get("broad_extra", [])
        if primary:
            return (
                [p.replace("-search", "") for p in primary],
                [p.replace("-search", "") for p in broad_extra],
            )
    return list(PORTAL_SKILLS.keys()), ["indeed-pl", "linkedin-pl"]


def filter_disabled(portals: List[str], settings: Settings) -> List[str]:
    disabled = {normalize_portal(p) for p in settings.scrapers_disabled_portals}
    return [p for p in portals if normalize_portal(p) not in disabled]


def resolve_portals_for_request(
    settings: Settings,
    *,
    broad: bool,
    explicit_portals: List[str] | None = None,
    portal_profile: str | None = None,
) -> List[str]:
    if explicit_portals:
        return filter_disabled(explicit_portals, settings)

    profiles = settings.scrapers_portal_profiles
    if profiles:
        profile_name = portal_profile or settings.scrapers_default_portal_profile
        portals = list(profiles.get(profile_name, []))
        if broad:
            portals.extend(profiles.get("broad", []))
        return filter_disabled(list(dict.fromkeys(portals)), settings)

    if broad:
        portals = TIER1_PORTALS + TIER2_PORTALS + TIER3_PORTALS
    else:
        portals = TIER1_PORTALS + TIER2_PORTALS

    primary, broad_extra = load_portal_lists(settings)
    if primary and not broad:
        portals = primary
    elif broad and broad_extra:
        portals = list(dict.fromkeys(primary + broad_extra))

    return filter_disabled(portals, settings)
