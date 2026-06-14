"""Cross-portal job deduplication by normalized company + title."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.jobs import SeenJobEntry

LEGAL_SUFFIXES = re.compile(
    r"\b("
    r"sp\.?\s*z\s*o\.?\s*o\.?|s\.?\s*a\.?|"
    r"spółka z ograniczoną odpowiedzialnością|"
    r"sp\.?\s*j\.?|sp\.?\s*k\.?|ltd\.?|inc\.?|gmbh"
    r")\b",
    re.I,
)
PARENS = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")


def normalize_company(name: str) -> str:
    s = (name or "").strip().lower()
    s = LEGAL_SUFFIXES.sub("", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_title(title: str) -> str:
    s = (title or "").strip().lower()
    s = PARENS.sub("", s)
    s = re.sub(
        r"\s*[-–—/]\s*(remote|zdaln[ae]|hybrid|hybryd\w*)\s*$",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def job_identity(company: str, title: str) -> tuple[str, str] | None:
    c = normalize_company(company)
    t = normalize_title(title)
    if not c or not t:
        return None
    return (c, t)


def identity_keys_from_seen(seen: dict[str, SeenJobEntry]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for job in seen.values():
        ident = job_identity(job.company, job.title)
        if ident:
            keys.add(ident)
    return keys
