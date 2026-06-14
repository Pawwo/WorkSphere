"""Shared seen_jobs state for scrape_batch."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.models.jobs import SeenJobEntry
from app.services.scrape.batch_context import BatchContext
from app.storage.files import seen_key, today_iso


def _settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    data.mkdir()
    (data / "job_scraper").mkdir()
    return Settings().model_copy(update={"data_dir": data.resolve()})


@pytest.mark.asyncio
async def test_batch_context_loads_and_flushes(tmp_path):
    settings = _settings(tmp_path)
    key = seen_key("https://example.com/job", "Acme", "COO")
    entry = SeenJobEntry(
        title="COO",
        company="Acme",
        url="https://example.com/job",
        first_seen=today_iso(),
        fit="medium",
        status="new",
    )
    settings.seen_jobs_path.write_text(
        json.dumps({"seen": {key: entry.model_dump()}}, ensure_ascii=False),
        encoding="utf-8",
    )

    ctx = BatchContext(settings)
    assert key in ctx.seen
    ctx.repo.upsert(
        seen_key("https://example.com/new", "Beta", "CTO"),
        SeenJobEntry(
            title="CTO",
            company="Beta",
            url="https://example.com/new",
            first_seen=today_iso(),
            fit="high",
            status="new",
        ),
    )
    await ctx.flush()

    reloaded = BatchContext(settings)
    assert len(reloaded.seen) == 2
