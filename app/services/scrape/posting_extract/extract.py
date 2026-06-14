"""Extract key job requirements from raw posting text."""

from __future__ import annotations

from app.services.job_fetcher import extract_linkedin_job_body
from app.services.scrape.posting_extract.clean import normalize_whitespace, strip_boilerplate_lines
from app.services.scrape.posting_extract.linkedin import extract_linkedin_sections

_MIN_LEN = 80
_MAX_LEN = 4000
_STORE_MAX = 15000


def extract_key_description(raw: str, *, portal: str = "", url: str = "") -> str:
    """Return requirements-focused text for seen_jobs.description."""
    if not raw or not raw.strip():
        return ""

    text = normalize_whitespace(raw)
    host = (url or "").lower()
    portal_l = (portal or "").lower()
    is_linkedin = "linkedin" in host or "linkedin" in portal_l

    # Section headers work across LinkedIn and PL job boards (Wymagania, Requirements, …).
    section = extract_linkedin_sections(text)
    if len(section) >= _MIN_LEN:
        return section[:_MAX_LEN]

    if is_linkedin:
        body = extract_linkedin_job_body(text)
        section = extract_linkedin_sections(body)
        if len(section) >= _MIN_LEN:
            return section[:_MAX_LEN]
        if len(body) >= _MIN_LEN:
            cleaned = strip_boilerplate_lines(body)
            if len(cleaned) >= _MIN_LEN:
                return cleaned[:_MAX_LEN]

    cleaned = strip_boilerplate_lines(text)
    if len(cleaned) >= _MIN_LEN:
        return cleaned[:_MAX_LEN]

    return text[:_MAX_LEN]


def description_for_storage(
    raw: str,
    *,
    portal: str = "",
    url: str = "",
    max_len: int = _STORE_MAX,
) -> str:
    """Normalize posting text for seen_jobs.description."""
    if not raw or not raw.strip():
        return ""
    extracted = extract_key_description(raw, portal=portal, url=url)
    if len(extracted) >= _MIN_LEN:
        return extracted[:max_len]
    return raw.strip()[:max_len]
