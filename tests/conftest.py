"""Pytest fixtures — markers and shared config."""

from __future__ import annotations

import pytest

from app.config import clear_settings_cache


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: tests requiring BC-250 LLM, SearXNG, or live scrapers",
    )


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    clear_settings_cache()
    yield
    clear_settings_cache()
