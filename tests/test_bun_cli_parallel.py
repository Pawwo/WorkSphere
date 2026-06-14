"""Parallel tier groups in BunCLIWrapper."""

from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.services.scrape.freshness import portal_strict_freshness


@pytest.mark.asyncio
async def test_parallel_tier_groups_runs_gather():
    from app.scrapers.bun_cli import BunCLIWrapper

    settings = Settings().model_copy(update={"scrapers_parallel_tier_groups": True})
    cli = BunCLIWrapper(settings)
    calls: list[list[str]] = []

    async def fake_group(portals, *args, **kwargs):
        calls.append(list(portals))
        return [(p, object()) for p in portals]

    with patch.object(cli, "_search_group", side_effect=fake_group):
        await cli.search_parallel_tiered(
            ["pracuj", "justjoin", "linkedin-pl"],
            "test query",
            days=2,
            limit=10,
        )

    assert len(calls) == 3
    assert set(calls[0]) == {"pracuj"}
    assert set(calls[1]) == {"justjoin"}
    assert set(calls[2]) == {"linkedin-pl"}


@pytest.mark.asyncio
async def test_slow_parallel_is_one_when_rocketjobs_in_group():
    from app.scrapers.bun_cli import BunCLIWrapper

    settings = Settings().model_copy(update={"scrapers_parallel_limit": 4})
    cli = BunCLIWrapper(settings)
    parallels: list[int] = []

    async def fake_group(portals, *args, **kwargs):
        parallels.append(kwargs.get("parallel", args[4] if len(args) > 4 else 0))
        return []

    with patch.object(cli, "_search_group", side_effect=fake_group):
        await cli.search_parallel_tiered(
            ["justjoin", "rocketjobs"],
            "docker",
            days=2,
            limit=10,
        )

    assert parallels[0] == 1


def test_portal_strict_freshness_overrides():
    assert (
        portal_strict_freshness(
            "praca-pl",
            global_strict=True,
            portal_overrides={"praca-pl": False},
        )
        is False
    )
    assert (
        portal_strict_freshness(
            "pracuj",
            global_strict=True,
            portal_overrides={"praca-pl": False},
        )
        is True
    )
