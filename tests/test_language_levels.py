"""Tests for CEFR level comparison."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.models.setup import LanguageEntry, WizardSection1, WizardState
from app.services.inbox.language_levels import (
    candidate_level,
    language_gap,
    level_rank,
    load_candidate_languages,
    token_to_level,
)
from app.services.profile.language_skills import parse_languages_text


def test_level_rank_order():
    assert level_rank("A1") < level_rank("B2") < level_rank("C1") < level_rank("native")


def test_token_to_level():
    assert token_to_level("english_fluent") == "C1"
    assert token_to_level("english_c1_plus") == "C2"


def test_language_gap_when_required_higher():
    profile = [LanguageEntry(language="english", level="B2")]
    assert language_gap(profile, language="english", level="C1") is True


def test_language_gap_when_candidate_meets():
    profile = [LanguageEntry(language="english", level="C1")]
    assert language_gap(profile, language="english", level="C1") is False


def test_language_gap_missing_language_in_profile():
    profile = [LanguageEntry(language="polish", level="native")]
    assert language_gap(profile, language="english", level="B2") is True


def test_parse_languages_text():
    skills = parse_languages_text("Polski (native), Angielski (B2)")
    assert len(skills) == 2
    assert skills[0].language == "polish"
    assert skills[1].level == "B2"


def test_load_candidate_languages(tmp_path: Path):
    setup = tmp_path / "setup"
    setup.mkdir()
    state = WizardState(
        section1=WizardSection1(
            full_name="Jan",
            location="Kraków",
            email="j@x.pl",
            language_skills=[
                LanguageEntry(language="polish", level="native"),
                LanguageEntry(language="english", level="B2"),
                LanguageEntry(language="german", level="A2"),
            ],
        )
    )
    (setup / "wizard_state.json").write_text(state.model_dump_json(), encoding="utf-8")
    settings = Settings().model_copy(update={"data_dir": tmp_path.resolve()})
    langs = load_candidate_languages(settings)
    assert len(langs) == 3
    assert candidate_level(langs, "english") == level_rank("B2")
