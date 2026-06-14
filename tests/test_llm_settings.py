"""LLM settings API and config persistence."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import yaml

from app.config import clear_settings_cache, get_settings, update_yaml_llm_settings
from app.services.llm_power_service import LlmPowerService
from app.services.llm_settings_service import (
    OPENROUTER_BASE_URL,
    apply_llm_base_url,
    apply_llm_settings,
    current_llm_config,
    is_local_bielik_endpoint,
    llm_presets,
    llm_test_message,
    test_llm_connection as run_llm_connection_test,
)


def test_llm_presets_include_8006_and_openrouter(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    clear_settings_cache()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({"llm": {"base_url": "http://192.168.0.112:8000/v1"}}),
        encoding="utf-8",
    )
    clear_settings_cache()
    presets = llm_presets(get_settings())
    ids = {p["id"] for p in presets}
    assert ids == {"8000", "8006", "openrouter"}
    assert any(p["base_url"].endswith(":8006/v1") for p in presets)
    assert any(p["base_url"] == OPENROUTER_BASE_URL for p in presets)


def test_update_yaml_llm_settings_persists_model_and_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        yaml.safe_dump({"llm": {"base_url": "http://192.168.0.112:8000/v1", "model": "bielik"}}),
        encoding="utf-8",
    )
    clear_settings_cache()
    update_yaml_llm_settings(
        base_url="http://192.168.0.112:8006/v1",
        model="meta-llama/llama-3.3-70b-instruct:free",
        api_key="sk-test-1234",
    )
    clear_settings_cache()
    settings = get_settings()
    assert settings.llm_base_url.rstrip("/") == "http://192.168.0.112:8006/v1"
    assert settings.llm_model == "meta-llama/llama-3.3-70b-instruct:free"
    assert settings.llm_api_key == "sk-test-1234"
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert raw["llm"]["api_key"] == "sk-test-1234"


def test_apply_llm_base_url_sets_custom(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "llm": {
                    "base_url": "http://192.168.0.112:8000/v1",
                    "wake_enabled": True,
                    "wake_url": "http://192.168.0.112:8099",
                }
            }
        ),
        encoding="utf-8",
    )
    clear_settings_cache()
    result = apply_llm_base_url("http://192.168.0.112:8006/v1")
    assert result["is_custom"] is False
    assert result["preset_id"] == "8006"
    assert result["is_local_bielik"] is True
    assert result["wake_active"] is True
    assert current_llm_config()["base_url"].endswith(":8006/v1")


def test_apply_llm_settings_masks_api_key_in_config(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "llm": {
                    "base_url": OPENROUTER_BASE_URL,
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                    "api_key": "sk-openrouter-abcd",
                    "wake_enabled": True,
                    "wake_url": "http://192.168.0.112:8099",
                }
            }
        ),
        encoding="utf-8",
    )
    clear_settings_cache()
    cfg = current_llm_config()
    assert cfg["api_key_set"] is True
    assert cfg["api_key_hint"] == "…abcd"
    assert "sk-openrouter-abcd" not in str(cfg)
    assert cfg["is_local_bielik"] is False
    assert cfg["wake_active"] is False
    assert cfg["preset_id"] == "openrouter"


def test_is_local_bielik_endpoint_external(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"llm": {"base_url": OPENROUTER_BASE_URL}}),
        encoding="utf-8",
    )
    clear_settings_cache()
    settings = get_settings()
    assert is_local_bielik_endpoint(settings) is False
    assert LlmPowerService(settings).enabled is False


def test_llm_test_message_external(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump({"llm": {"base_url": OPENROUTER_BASE_URL}}),
        encoding="utf-8",
    )
    clear_settings_cache()
    msg = llm_test_message(get_settings())
    assert "BC-250" not in msg
    assert OPENROUTER_BASE_URL in msg


@pytest.mark.asyncio
async def test_llm_test_connection_wakes_when_local_bielik(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "llm": {
                    "base_url": "http://192.168.0.112:8006/v1",
                    "wake_enabled": True,
                    "wake_url": "http://192.168.0.112:8099",
                }
            }
        ),
        encoding="utf-8",
    )
    clear_settings_cache()
    settings = get_settings()
    with patch(
        "app.services.llm_power_service.LlmPowerService.wake_and_prepare",
        new_callable=AsyncMock,
        return_value={"ok": True, "wake_ok": True},
    ) as wake_mock:
        with patch(
            "app.services.llm_settings_service.BielikClient.healthcheck_extended",
            new_callable=AsyncMock,
            return_value={"ok": True, "model": "test-model"},
        ):
            health = await run_llm_connection_test(settings, wake=True)
    wake_mock.assert_awaited_once()
    assert health["ok"] is True
    assert health["wake"]["wake_ok"] is True


@pytest.mark.asyncio
async def test_llm_test_connection_skips_wake_for_openrouter(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "llm": {
                    "base_url": OPENROUTER_BASE_URL,
                    "wake_enabled": True,
                    "wake_url": "http://192.168.0.112:8099",
                }
            }
        ),
        encoding="utf-8",
    )
    clear_settings_cache()
    settings = get_settings()
    with patch(
        "app.services.llm_power_service.LlmPowerService.wake_and_prepare",
        new_callable=AsyncMock,
    ) as wake_mock:
        with patch(
            "app.services.llm_settings_service.BielikClient.healthcheck_extended",
            new_callable=AsyncMock,
            return_value={"ok": True, "model": "cloud-model"},
        ):
            health = await run_llm_connection_test(settings, wake=True)
    wake_mock.assert_not_awaited()
    assert health["ok"] is True
    assert "wake" not in health


def test_apply_llm_settings_keeps_api_key_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.ROOT", tmp_path)
    (tmp_path / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "llm": {
                    "base_url": OPENROUTER_BASE_URL,
                    "model": "meta-llama/llama-3.3-70b-instruct:free",
                    "api_key": "sk-keep-me",
                }
            }
        ),
        encoding="utf-8",
    )
    clear_settings_cache()
    apply_llm_settings(model="other-model")
    clear_settings_cache()
    assert get_settings().llm_api_key == "sk-keep-me"
    assert get_settings().llm_model == "other-model"
