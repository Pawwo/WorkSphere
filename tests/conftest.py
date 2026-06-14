"""Pytest fixtures — markers and shared config."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import clear_settings_cache

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
CANDIDATE_PROFILE = FIXTURES_DIR / "candidate_profile.md"
WIZARD_STATE_JSON = FIXTURES_DIR / "wizard_state.json"
WOLTERS_CV_HTML = FIXTURES_DIR / "cv" / "wolters_sample.html"
WOLTERS_APP_DIR = FIXTURES_DIR / "applications" / "wolters_kluwer_polska_sp_z_oo"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: tests requiring local GPU LLM, SearXNG, or live scrapers",
    )


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    clear_settings_cache()
    yield
    clear_settings_cache()
