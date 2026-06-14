"""Section header patterns for job posting extraction (EN + PL)."""

from __future__ import annotations

import re

# Tier 1: specific section titles (preferred).
REQUIREMENTS_HEADERS_TIER1: tuple[str, ...] = (
    r"What we['\u2019]re looking for",
    r"What we are looking for",
    r"What you need",
    r"Essential [Qq]ualifications",
    r"Minimum [Qq]ualifications",
    r"Qualifications",
    r"Requirements",
    r"Must have",
    r"Must-have",
    r"Wymagania",
    r"Nasze oczekiwania",
    r"Oczekujemy",
    r"Kim jesteś",
)

# Tier 2: generic — only if tier 1 misses (prone to login-form false positives).
REQUIREMENTS_HEADERS_TIER2: tuple[str, ...] = (
    r"Your profile",
    r"Your skills",
    r"About you",
    r"Twój profil",
)

REQUIREMENTS_HEADERS: tuple[str, ...] = REQUIREMENTS_HEADERS_TIER1 + REQUIREMENTS_HEADERS_TIER2

RESPONSIBILITIES_HEADERS: tuple[str, ...] = (
    r"What you['\u2019]ll be working on",
    r"What you will be working on",
    r"What you['\u2019]ll do",
    r"What you will do",
    r"Responsibilities",
    r"Your responsibilities",
    r"Obowiązki",
    r"Zakres obowiązków",
    r"Na tym stanowisku",
)

SECTION_END_MARKERS: tuple[str, ...] = (
    r"Seniority level",
    r"Employment type",
    r"Job function",
    r"Industries",
    r"Poziom w hierarchii",
    r"Rodzaj zatrudnienia",
    r"Similar jobs",
    r"Podobne oferty",
    r"People also viewed",
    r"Set alert",
    r"Referrals",
    r"Polecenia",
    r"Oferujemy",
    r"What we offer",
    r"Benefits",
    r"Benefity",
)


def compile_header_patterns(headers: tuple[str, ...]) -> list[re.Pattern[str]]:
    return [re.compile(rf"(?i)(?:^|\s){pat}\s*:?\s*", re.MULTILINE) for pat in headers]


REQUIREMENTS_PATTERNS = compile_header_patterns(REQUIREMENTS_HEADERS)
RESPONSIBILITIES_PATTERNS = compile_header_patterns(RESPONSIBILITIES_HEADERS)
END_PATTERNS = [re.compile(rf"(?i){pat}") for pat in SECTION_END_MARKERS]
