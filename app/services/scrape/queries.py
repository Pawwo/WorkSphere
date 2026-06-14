"""Batch scrape query resolution."""

from __future__ import annotations

from app.config import Settings
from app.models.jobs import ScrapeBatchRequest
from app.services.profile_service import ProfileService
from app.services.search_queries import append_city_to_query, resolve_scrape_queries


def dedupe_queries(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            out.append(q)
    return out


def wizard_roles_and_city(
    settings: Settings,
    *,
    append_city: bool,
) -> tuple[list[str], str]:
    state = ProfileService(settings).load_wizard_state()
    roles: list[str] = []
    if state.section9 and state.section9.role_titles:
        roles = [r.strip() for r in state.section9.role_titles if r.strip()]
    elif state.section7 and state.section7.target_roles:
        roles = [r.strip() for r in state.section7.target_roles if r.strip()]
    city = ""
    if append_city and state.section9 and state.section9.city:
        city = state.section9.city.strip()
    return roles, city


def resolve_batch_queries(settings: Settings, request: ScrapeBatchRequest) -> list[str]:
    if request.roles:
        roles = [r.strip() for r in request.roles if r and r.strip()]
        _, city = wizard_roles_and_city(settings, append_city=request.append_city)
        queries = [
            append_city_to_query(role, city) if city else role for role in roles
        ]
        return dedupe_queries(queries)

    if request.max_categories is not None:
        max_cats = request.max_categories
    elif request.broad:
        max_cats = 99
    else:
        max_cats = 3
    queries = resolve_scrape_queries(broad=request.broad, max_categories=max_cats)
    if queries:
        if request.append_city:
            _, city = wizard_roles_and_city(settings, append_city=True)
            if city:
                return dedupe_queries([append_city_to_query(q, city) for q in queries])
        return queries

    roles, city = wizard_roles_and_city(settings, append_city=request.append_city)
    return dedupe_queries(
        [append_city_to_query(role, city) if city else role for role in roles]
    )
