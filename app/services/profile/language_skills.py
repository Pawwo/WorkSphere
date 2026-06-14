"""Structured language skills for profile wizard and CV."""

from __future__ import annotations

import re
from typing import Literal

from app.models.setup import LanguageEntry, LanguageCode, LanguageLevel

LANGUAGE_OPTIONS: list[tuple[LanguageCode, str]] = [
    ("polish", "Polski"),
    ("english", "Angielski"),
    ("german", "Niemiecki"),
    ("french", "Francuski"),
    ("spanish", "Hiszpański"),
    ("italian", "Włoski"),
    ("ukrainian", "Ukraiński"),
    ("other", "Inny"),
]

LEVEL_OPTIONS: list[tuple[LanguageLevel, str]] = [
    ("native", "Ojczysty"),
    ("C2", "C2"),
    ("C1", "C1"),
    ("B2", "B2"),
    ("B1", "B1"),
    ("A2", "A2"),
    ("A1", "A1"),
]

_LANGUAGE_LABEL_PL: dict[LanguageCode, str] = dict(LANGUAGE_OPTIONS)
_LEVEL_LABEL_PL: dict[LanguageLevel, str] = dict(LEVEL_OPTIONS)

_LANGUAGE_ALIASES: dict[str, LanguageCode] = {
    "polski": "polish",
    "polish": "polish",
    "pl": "polish",
    "angielski": "english",
    "english": "english",
    "en": "english",
    "niemiecki": "german",
    "german": "german",
    "deutsch": "german",
    "de": "german",
    "francuski": "french",
    "french": "french",
    "fr": "french",
    "hiszpański": "spanish",
    "hiszpanski": "spanish",
    "spanish": "spanish",
    "es": "spanish",
    "włoski": "italian",
    "wloski": "italian",
    "italian": "italian",
    "it": "italian",
    "ukraiński": "ukrainian",
    "ukrainski": "ukrainian",
    "ukrainian": "ukrainian",
    "uk": "ukrainian",
}

_LEVEL_ALIASES: dict[str, LanguageLevel] = {
    "native": "native",
    "ojczysty": "native",
    "ojczysty język": "native",
    "mother tongue": "native",
    "c2": "C2",
    "c1": "C1",
    "c1+": "C2",
    "b2": "B2",
    "b1": "B1",
    "a2": "A2",
    "a1": "A1",
    "fluent": "C1",
    "excellent": "C1",
    "advanced": "B2",
    "zaawansowany": "B2",
    "średniozaawansowany": "B1",
    "sredniozaawansowany": "B1",
    "podstawowy": "A2",
    "beginner": "A1",
}


def normalize_language_code(name: str) -> LanguageCode | None:
    key = (name or "").strip().lower()
    if not key:
        return None
    if key in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[key]
    for alias, code in _LANGUAGE_ALIASES.items():
        if alias in key or key in alias:
            return code
    return None


def normalize_level(level: str) -> LanguageLevel | None:
    key = (level or "").strip().lower()
    if not key:
        return None
    if key in _LEVEL_ALIASES:
        return _LEVEL_ALIASES[key]
    m = re.search(r"\b(c2|c1|b2|b1|a2|a1)\b", key, re.I)
    if m:
        return m.group(1).upper()  # type: ignore[return-value]
    return None


def parse_languages_text(text: str) -> list[LanguageEntry]:
    """Parse legacy free-text e.g. 'Polski (native), Angielski (B2)'."""
    if not (text or "").strip():
        return []
    entries: list[LanguageEntry] = []
    for part in re.split(r"[,;|]", text):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(.+?)\s*[\(\-–—]\s*(.+?)\s*\)?$", part)
        if m:
            lang = normalize_language_code(m.group(1))
            level = normalize_level(m.group(2))
        else:
            tokens = part.split()
            lang = normalize_language_code(tokens[0]) if tokens else None
            level = normalize_level(" ".join(tokens[1:])) if len(tokens) > 1 else None
        if lang and level:
            entries.append(LanguageEntry(language=lang, level=level))
    return entries


def format_languages_line(skills: list[LanguageEntry], *, locale: Literal["pl", "en"] = "pl") -> str:
    if not skills:
        return ""
    parts: list[str] = []
    for entry in skills:
        if locale == "en":
            lang = entry.language.replace("_", " ").title()
            level = entry.level if entry.level != "native" else "native"
        else:
            lang = _LANGUAGE_LABEL_PL.get(entry.language, entry.language)
            level = _LEVEL_LABEL_PL.get(entry.level, entry.level)
        parts.append(f"{lang} ({level})")
    return ", ".join(parts)


def format_languages_cv_line(skills: list[LanguageEntry], cv_lang: str) -> str:
    """CV languages line using em-dash separators."""
    if not skills:
        return languages_line_fallback(cv_lang)
    locale: Literal["pl", "en"] = "en" if cv_lang.startswith("en") else "pl"
    sep = " | " if locale == "en" else " | "
    dash = " — " if locale == "pl" else " — "
    parts: list[str] = []
    for entry in skills:
        if locale == "en":
            lang = entry.language.replace("_", " ").title()
            level = entry.level if entry.level != "native" else "native"
        else:
            lang = _LANGUAGE_LABEL_PL.get(entry.language, entry.language)
            level = _LEVEL_LABEL_PL.get(entry.level, entry.level)
        parts.append(f"{lang}{dash}{level}")
    return sep.join(parts)


def languages_line_fallback(cv_lang: str) -> str:
    if cv_lang.startswith("en"):
        return "English — advanced | Polish — native"
    return "Polski — ojczysty | Angielski — zaawansowany"


def ensure_language_skills(
    language_skills: list[LanguageEntry] | None,
    languages_text: str = "",
) -> list[LanguageEntry]:
    if language_skills:
        return [s for s in language_skills if s.language and s.level]
    return parse_languages_text(languages_text)
