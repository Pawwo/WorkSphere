"""BunCLIWrapper healthcheck — disabled portals."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.scrapers.bun_cli import BunCLIWrapper


@pytest.mark.asyncio
async def test_healthcheck_ignores_missing_disabled_portal(tmp_path, monkeypatch):
    skills_root = tmp_path / ".agents/skills"
    (skills_root / "node_modules").mkdir(parents=True)

    def stub_cli(skill_name: str):
        cli = skills_root / skill_name / "cli" / "src" / "cli.ts"
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_text("// stub")
        return cli

    for skill in (
        "pracuj-search",
        "praca-pl-search",
        "justjoin-search",
        "nofluffjobs-search",
        "theprotocol-search",
        "rocketjobs-search",
        "linkedin-pl-search",
    ):
        stub_cli(skill)

    settings = Settings().model_copy(
        update={
            "repo_root": tmp_path,
            "scrapers_disabled_portals": ["indeed-pl"],
            "bun_path": "bun",
        }
    )
    cli = BunCLIWrapper(settings)

    proc = MagicMock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(b"1.3.14", b""))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    result = await cli.healthcheck()

    assert result["ok"] is True
    assert result["portals"]["indeed-pl"]["required"] is False
    assert result["portals"]["indeed-pl"]["cli_exists"] is False
    assert result["portals"]["pracuj"]["required"] is True
    assert result["portals"]["pracuj"]["cli_exists"] is True
