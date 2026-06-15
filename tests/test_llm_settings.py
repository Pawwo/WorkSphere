"""Tests for LLM settings service."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.config import ROOT, clear_settings_cache, get_settings
from app.services.llm_settings_service import (
    apply_llm_base_url,
    apply_llm_settings,
    current_llm_config,
    llm_presets,
    llm_test_message,
)


def _write_config(data: dict, root: Path) -> None:
    path = root / "config.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    clear_settings_cache()


def test_llm_presets_include_local_and_openrouter():
    presets = llm_presets()
    ids = {p["id"] for p in presets}
    assert "local" in ids
    assert "openrouter" in ids
    local = next(p for p in presets if p["id"] == "local")
    assert local["base_url"] == "http://127.0.0.1:8006/v1"


def test_apply_llm_settings_updates_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    _write_config({"llm": {"base_url": "http://127.0.0.1:8000/v1", "model": "old"}}, tmp_path)
    result = apply_llm_settings(
        base_url="http://127.0.0.1:8006/v1",
        model="test-model",
    )
    settings = get_settings()
    assert settings.llm_base_url.rstrip("/") == "http://127.0.0.1:8006/v1"
    assert settings.llm_model == "test-model"
    assert result["preset_id"] == "local"


def test_apply_llm_base_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    _write_config({"llm": {"base_url": "http://127.0.0.1:8000/v1", "model": "bielik"}}, tmp_path)
    result = apply_llm_base_url("http://127.0.0.1:8006/v1")
    assert result["base_url"] == "http://127.0.0.1:8006/v1"
    assert get_settings().llm_base_url.rstrip("/") == "http://127.0.0.1:8006/v1"


def test_current_llm_config_custom_url(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    _write_config({"llm": {"base_url": "https://api.example.com/v1", "model": "x"}}, tmp_path)
    cfg = current_llm_config()
    assert cfg["is_custom"] is True
    assert cfg["preset_id"] is None


def test_llm_test_message_generic():
    msg = llm_test_message()
    assert "Testuję połączenie" in msg
