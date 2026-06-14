"""CEFR level comparison for profile-aware language triage."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.models.setup import LanguageEntry, LanguageCode, LanguageLevel
from app.services.profile.language_skills import ensure_language_skills, normalize_language_code

if TYPE_CHECKING:
    from app.config import Settings

LEVEL_RANK: dict[LanguageLevel, int] = {
    "A1": 1,
    "A2": 2,
    "B1": 3,
    "B2": 4,
    "C1": 5,
    "C2": 6,
    "native": 7,
}

TOKEN_TO_LEVEL: dict[str, LanguageLevel] = {
    "english_fluent": "C1",
    "english_excellent": "C1",
    "english_c1": "C1",
    "english_c1_plus": "C2",
    "german_fluent": "C1",
    "german_excellent": "C1",
    "german_c1": "C1",
    "german_c1_plus": "C2",
    "french_fluent": "C1",
    "french_excellent": "C1",
    "french_c1": "C1",
    "french_c1_plus": "C2",
}


def level_rank(level: LanguageLevel | str | None) -> int:
    if not level:
        return 0
    return LEVEL_RANK.get(level, 0)  # type: ignore[arg-type]


def token_to_level(token: str | None) -> LanguageLevel | None:
    if not token:
        return None
    return TOKEN_TO_LEVEL.get(token)


def candidate_level(
    profile_skills: list[LanguageEntry],
    lang_code: LanguageCode | str,
) -> int:
    code = lang_code if isinstance(lang_code, str) else lang_code
    for entry in profile_skills:
        if entry.language == code:
            return level_rank(entry.level)
    return 0


def language_gap(
    profile_skills: list[LanguageEntry],
    *,
    language: LanguageCode | str,
    level: LanguageLevel | str,
) -> bool:
    required = level_rank(level)  # type: ignore[arg-type]
    if required <= 0:
        return False
    have = candidate_level(profile_skills, language)
    return required > have


def load_candidate_languages(settings: Optional[Settings] = None) -> list[LanguageEntry]:
    from app.config import get_settings
    from app.services.profile_service import ProfileService

    settings = settings or get_settings()
    state = ProfileService(settings).load_wizard_state()
    if not state.section1:
        return []
    s1 = state.section1
    return ensure_language_skills(s1.language_skills, s1.languages)


def normalize_requirement_language(name: str) -> LanguageCode | None:
    return normalize_language_code(name)
