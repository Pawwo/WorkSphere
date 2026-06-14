"""LinkedIn-specific section extraction from plain text."""

from __future__ import annotations

import re

from app.services.scrape.posting_extract.clean import (
    normalize_whitespace,
    strip_boilerplate_lines,
    trim_trailing_chrome,
)
from app.services.scrape.posting_extract.section_headers import (
    END_PATTERNS,
    REQUIREMENTS_HEADERS_TIER1,
    REQUIREMENTS_HEADERS_TIER2,
    compile_header_patterns,
    RESPONSIBILITIES_PATTERNS,
)

REQUIREMENTS_TIER1_PATTERNS = compile_header_patterns(REQUIREMENTS_HEADERS_TIER1)
REQUIREMENTS_TIER2_PATTERNS = compile_header_patterns(REQUIREMENTS_HEADERS_TIER2)

_MAX_SECTION = 4000


def _login_context(text: str, pos: int) -> bool:
    window = text[max(0, pos - 100) : pos + 100].lower()
    markers = (
        "sign in",
        "join now",
        "email or phone",
        "forgot password",
        "user agreement",
        "cookie policy",
        "tailor my resume",
        "evaluate your skills",
    )
    return any(m in window for m in markers)


def _find_section_start(text: str, patterns: list[re.Pattern[str]]) -> int | None:
    candidates: list[int] = []
    for pat in patterns:
        for m in pat.finditer(text):
            if _login_context(text, m.start()):
                continue
            candidates.append(m.end())
    if not candidates:
        return None
    # Requirements blocks usually follow the main JD (prefer later match).
    return max(candidates)


def _find_section_end(text: str, start: int) -> int:
    end = len(text)
    for pat in END_PATTERNS:
        m = pat.search(text, start)
        if m and m.start() > start + 50:
            end = min(end, m.start())
    return end


def _split_inline_requirements(block: str) -> list[str]:
    """LinkedIn often concatenates bullets into one line after the section header."""
    block = re.sub(r"\s+", " ", block).strip()
    if not block:
        return []
    parts = re.split(
        r"(?<=[.!?])\s+(?=[A-Z])|(?<=[a-z])\s+(?=Around \d)|(?<=[a-z])\s+(?=Hands-on )|"
        r"(?<=[a-z])\s+(?=Familiarity with )|(?<=[a-z])\s+(?=Experience working )|"
        r"(?<=[a-z])\s+(?=Solid understanding )|(?<=[a-z])\s+(?=Strong )|(?<=[a-z])\s+(?=Ability to )",
        block,
    )
    return [p.strip() for p in parts if len(p.strip()) > 10]


def _lines_to_bullets(block: str) -> str:
    block = strip_boilerplate_lines(block)
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if len(lines) == 1 and len(lines[0]) > 120:
        lines = _split_inline_requirements(lines[0])
    if not lines:
        return ""
    # Merge short continuation lines
    bullets: list[str] = []
    for ln in lines:
        if bullets and len(ln) < 40 and not re.match(r"^[\-\*•]", ln):
            bullets[-1] = f"{bullets[-1]} {ln}"
        else:
            bullets.append(ln)
    return trim_trailing_chrome("\n".join(bullets[:40]))


def extract_linkedin_sections(text: str) -> str:
    """Return requirements (preferred) or responsibilities section from LinkedIn plain text."""
    if not text:
        return ""

    req_start = _find_section_start(text, REQUIREMENTS_TIER1_PATTERNS)
    if req_start is None:
        req_start = _find_section_start(text, REQUIREMENTS_TIER2_PATTERNS)
    if req_start is not None:
        req_end = _find_section_end(text, req_start)
        section = text[req_start:req_end].strip()
        result = _lines_to_bullets(section)
        if len(result) >= 80:
            return result[:_MAX_SECTION]

    resp_start = _find_section_start(text, RESPONSIBILITIES_PATTERNS)
    if resp_start is not None:
        resp_end = _find_section_end(text, resp_start)
        section = text[resp_start:resp_end].strip()
        result = _lines_to_bullets(section)
        if len(result) >= 80:
            return result[:_MAX_SECTION]

    return ""
