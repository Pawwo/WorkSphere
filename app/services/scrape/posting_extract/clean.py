"""Remove boilerplate from posting text blocks."""

from __future__ import annotations

import re

_BOILERPLATE_LINE = re.compile(
    r"(?i)^(sign in to linkedin|join now|join or sign in|report this job|save\s*$|"
    r"agree & join linkedin|user agreement|cookie policy|"
    r"see who .+ has hired|direct message the job poster|"
    r"get notified about new .+ jobs|explore top content on linkedin)"
)

_BULLET_PREFIX = re.compile(r"^[\s•\-\*\u2022]+")


def strip_boilerplate_lines(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _BOILERPLATE_LINE.match(stripped):
            continue
        if len(stripped) < 3:
            continue
        lines.append(_BULLET_PREFIX.sub("", stripped).strip())
    return "\n".join(lines)


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text).strip()
    return re.sub(r"(?i)\s*show more\s*show less\s*$", "", text).strip()


def trim_trailing_chrome(text: str) -> str:
    return re.sub(r"(?i)\s*(show more\s*show less|set alert|see who you know)\s*$", "", text).strip()
