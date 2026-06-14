"""Keyword pre-filter for scrape flow (shared with workflow_triage)."""

from __future__ import annotations

import re
from typing import Literal, Optional

REJECT_KEYWORDS = (
    r"python developer",
    r"senior python",
    r"data engineer",
    r"integration architect",
    r"helpdesk manager",
    r"kasjer",
    r"magazynier",
    r"sprzedaw",
    r"konsultant.*niemiec",
    r"konsultant.*klienta",
    r"operator ",
    r"księgow",
    r"inspektor",
    r"spawania",
    r"key account manager",
    r"software engineering manager",
    r"sailpoint",
    r"identityiq",
    r"bangkok",
    r"podobne oferty",
    r"owoców i warzyw",
    r"murex back office",
)


def _blob(title: str, company: str) -> str:
    blob = f"{title} {company}".lower()
    return re.sub(r"&amp;", "&", blob)


def is_reject_job(title: str, company: str) -> bool:
    """True when job should not enter seen_jobs at all."""
    blob = _blob(title, company)
    for pat in REJECT_KEYWORDS:
        if re.search(pat, blob, re.I):
            return True
    return False


def keyword_fit_hint(title: str, company: str) -> Optional[Literal["low"]]:
    """Return low when job clearly mismatches profile; None if LLM should decide."""
    if is_reject_job(title, company):
        return "low"
    return None
