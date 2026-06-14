"""Detect language level requirements in job posting text."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from app.models.jobs import SeenJobEntry
from app.models.setup import LanguageCode, LanguageLevel
from app.services.inbox.language_levels import token_to_level
from app.services.job_fetcher import _strip_html
from app.services.scrape.posting_extract import description_for_storage
from app.storage.files import is_http_url

logger = logging.getLogger(__name__)

_MIN_BLOB_LEN = 80
_MAX_STORED_DESC = 15000

_ENGLISH = r"english|angielski"
_GERMAN = r"german|niemieck|deutsch"
_FRENCH = r"french|francusk|français|francais"
_OTHER_LANG = (
    r"polish|polski|german|niemieck|french|francusk|spanish|hiszpańsk|italian|włosk|"
    r"russian|rosyjsk|ukrainian|ukraińsk|portuguese|portugalsk|dutch|holendersk|"
    r"czech|czesk|norwegian|norwesk|danish|duńsk|swedish|szwedzk|finnish|fińsk"
)
_B2_C1 = re.compile(r"b2\s*/\s*c1", re.I)

_LANG_SPECS: list[tuple[LanguageCode, str, str]] = [
    ("english", _ENGLISH, "english"),
    ("german", _GERMAN, "german"),
    ("french", _FRENCH, "french"),
]


@dataclass(frozen=True)
class LanguageRequirement:
    language: LanguageCode
    level: LanguageLevel
    token: str | None = None
    evidence: str | None = None


def job_posting_blob(job: SeenJobEntry) -> str:
    parts = [job.title or "", job.salary_raw or "", job.description or ""]
    return " ".join(p.strip() for p in parts if p.strip())


def fetch_posting_text_sync(url: str, *, timeout: float = 20.0) -> str | None:
    """Fetch posting HTML and return plain text (for triage backfill)."""
    if not is_http_url(url):
        return None
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "WorkSphere/0.1"})
            response.raise_for_status()
            if "html" in response.headers.get("content-type", ""):
                text = _strip_html(response.text)
            else:
                text = response.text.strip()
        return text[:_MAX_STORED_DESC] if len(text) >= 30 else None
    except Exception as exc:
        logger.debug("Posting fetch failed for %s: %s", url, exc)
        return None


def _has_stored_posting_body(job: SeenJobEntry) -> bool:
    return bool((job.salary_raw or "").strip() or (job.description or "").strip())


def ensure_posting_blob(job: SeenJobEntry) -> tuple[str, str | None]:
    """Return posting text; optionally fetch and return description to persist."""
    blob = job_posting_blob(job)
    if _has_stored_posting_body(job) and len(blob) >= _MIN_BLOB_LEN:
        return blob, None
    if not is_http_url(job.url):
        return blob, None
    fetched = fetch_posting_text_sync(job.url)
    if not fetched:
        return blob, None
    stored = description_for_storage(
        fetched, portal=job.portal or "", url=job.url or ""
    )
    parts = [job.title or "", job.salary_raw or "", stored]
    merged = " ".join(p.strip() for p in parts if p.strip())
    return merged, stored


def _has_b2_c1(text: str) -> bool:
    return bool(_B2_C1.search(text))


def _fluent_match(text: str, lang_pat: str) -> bool:
    for m in re.finditer(
        rf"fluent(?:\s+\w+){{0,6}}\s+({lang_pat})\b|({lang_pat})(?:\s+\w+){{0,6}}\s+fluent",
        text,
        re.I,
    ):
        span = m.group(0).lower()
        if re.search(rf"fluent\s+in\s+({_OTHER_LANG})\b", span, re.I):
            continue
        return True
    return False


def _excellent_match(text: str, lang_pat: str) -> bool:
    return bool(
        re.search(
            rf"excellent(?:\s+\w+){{0,6}}\s+({lang_pat})\b|({lang_pat})(?:\s+\w+){{0,6}}\s+excellent",
            text,
            re.I,
        )
    )


def _c1_match(text: str, lang_pat: str, prefix: str) -> str | None:
    if _has_b2_c1(text):
        return None
    lang_re = re.compile(lang_pat, re.I)
    patterns = [
        (r"c1\+|\(c1\+\)", f"{prefix}_c1_plus"),
        (r"\(c1\)|\bc1/c2\b", f"{prefix}_c1"),
        (r"\bc1\b", f"{prefix}_c1"),
    ]
    for pat, token in patterns:
        for m in re.finditer(pat, text, re.I):
            window = text[max(0, m.start() - 60) : m.end() + 60]
            if lang_re.search(window):
                return token
    return None


def _detect_for_language(
    text: str,
    *,
    language: LanguageCode,
    lang_pat: str,
    prefix: str,
) -> LanguageRequirement | None:
    lower = text.lower()
    if _fluent_match(lower, lang_pat):
        return LanguageRequirement(
            language=language,
            level="C1",
            token=f"{prefix}_fluent",
            evidence="fluent",
        )
    if _excellent_match(lower, lang_pat):
        return LanguageRequirement(
            language=language,
            level="C1",
            token=f"{prefix}_excellent",
            evidence="excellent",
        )
    c1_token = _c1_match(lower, lang_pat, prefix)
    if c1_token:
        level = token_to_level(c1_token) or "C1"
        return LanguageRequirement(
            language=language,
            level=level,
            token=c1_token,
            evidence=c1_token,
        )
    return None


def extract_language_requirements(text: str) -> list[LanguageRequirement]:
    """Return detected language requirements (highest per language)."""
    if not text or not text.strip():
        return []

    blob = re.sub(r"&amp;", "&", text)
    found: dict[LanguageCode, LanguageRequirement] = {}
    for language, lang_pat, prefix in _LANG_SPECS:
        req = _detect_for_language(blob, language=language, lang_pat=lang_pat, prefix=prefix)
        if req:
            found[language] = req
    return list(found.values())


def detect_strict_english_requirement(text: str) -> tuple[bool, str | None]:
    """Legacy helper: (has_english_requirement, token)."""
    reqs = extract_language_requirements(text)
    for req in reqs:
        if req.language == "english" and req.token:
            return True, req.token
    return False, None
