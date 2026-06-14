"""BunCLI batch flags for praca-pl listing-only."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.scrapers.bun_cli import BunCLIWrapper


def test_portal_cli_args_praca_pl_batch_listing_only():
    cli = BunCLIWrapper(Settings())
    batch_args = cli._portal_cli_args("praca-pl", "COO", is_batch=True)
    assert "--listing-only" in batch_args
    assert batch_args[batch_args.index("--listing-only") + 1] == "true"

    ui_args = cli._portal_cli_args("praca-pl", "COO", is_batch=False)
    assert ui_args[ui_args.index("--listing-only") + 1] == "false"


@pytest.mark.asyncio
async def test_search_skips_retry_in_batch():
    cli = BunCLIWrapper(Settings().model_copy(update={"scrapers_retry_on_timeout": 2}))
    calls = 0

    async def fake_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        from app.scrapers.bun_cli import BunCLIError

        raise BunCLIError("praca-pl", "Timeout po 30s", "TIMEOUT")

    with patch.object(cli, "_search_once", side_effect=fake_once):
        with pytest.raises(Exception):
            await cli.search("praca-pl", "test", is_batch=True)
    assert calls == 1

    calls = 0
    with patch.object(cli, "_search_once", side_effect=fake_once):
        with pytest.raises(Exception):
            await cli.search("praca-pl", "test", is_batch=False)
    assert calls == 3


@pytest.mark.asyncio
async def test_search_parallel_tiered_passes_is_batch():
    cli = BunCLIWrapper(Settings())
    captured: dict = {}

    async def fake_group(portals, *args, **kwargs):
        captured.update(kwargs)
        return []

    with patch.object(cli, "_search_group", side_effect=fake_group):
        await cli.search_parallel_tiered(["pracuj", "praca-pl"], "q", is_batch=True)
    assert captured.get("is_batch") is True


def test_portal_cli_args_indeed_pl_batch_detail_limit_zero():
    cli = BunCLIWrapper(Settings())
    batch_args = cli._portal_cli_args("indeed-pl", "python", is_batch=True)
    assert "--detail-limit" in batch_args
    assert batch_args[batch_args.index("--detail-limit") + 1] == "0"


def test_batch_context_praca_pl_circuit():
    from app.services.scrape.batch_context import BatchContext

    settings = Settings()
    ctx = BatchContext(settings)
    assert not ctx.praca_pl_circuit_open
    ctx.record_praca_pl_timeout()
    assert not ctx.praca_pl_circuit_open
    ctx.record_praca_pl_timeout()
    assert ctx.praca_pl_circuit_open
