"""Regression: post-batch hooks must not crash inside a running event loop."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.post_batch_service import run_post_batch, run_post_batch_async


@pytest.mark.asyncio
async def test_run_post_batch_async_from_running_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("POST_BATCH_AUTO_TRIAGE", "1")
    monkeypatch.setenv("POST_BATCH_PI_COMPARE", "0")

    fake_triage = {"skipped": 0, "priority": 1, "review": 2, "top10": []}
    with patch("app.services.post_batch_service._run_triage", return_value=fake_triage) as triage:
        summary = await run_post_batch_async()

    assert summary["triage"] == fake_triage
    triage.assert_called_once()


@pytest.mark.asyncio
async def test_scrape_batch_post_hook_no_asyncio_run(monkeypatch):
    """run_batch must complete post_batch without asyncio.run() crash."""
    monkeypatch.setenv("POST_BATCH_AUTO_TRIAGE", "1")
    monkeypatch.setenv("POST_BATCH_PI_COMPARE", "0")

    from app.models.jobs import ScrapeBatchRequest, ScrapeBatchResponse, ScrapeResponse
    from app.services.scrape_service import ScrapeService

    fake_batch = ScrapeBatchResponse(
        queries_run=1,
        total_found=0,
        new_count=0,
        results=[],
        new_jobs=[],
        portal_errors=[],
    )

    svc = ScrapeService()
    svc.resolve_batch_queries = MagicMock(return_value=["test query"])
    svc.run = AsyncMock(
        return_value=ScrapeResponse(
            run_id=1,
            query="test query",
            total_found=0,
            new_count=0,
            results=[],
            portal_errors=[],
        )
    )

    with (
        patch.object(svc.llm, "is_ready", AsyncMock(return_value=True)),
        patch("app.services.scrape_service.LlmPowerService") as power_cls,
        patch("app.services.scrape_service.BatchContext") as batch_ctx_cls,
        patch(
            "app.services.post_batch_service._run_triage",
            return_value={"skipped": 0, "priority": 0, "review": 0, "top10": []},
        ),
    ):
        batch_ctx_cls.return_value.flush = AsyncMock()
        batch_ctx_cls.return_value.seen = {}
        power_cls.return_value.enabled = False

        result = await svc.run_batch(ScrapeBatchRequest())

    assert result.queries_run == 1


def test_run_triage_safe_when_called_from_sync_context(tmp_path, monkeypatch):
    """run_post_batch sync path still works outside an event loop."""
    monkeypatch.setenv("POST_BATCH_AUTO_TRIAGE", "1")
    monkeypatch.setenv("POST_BATCH_PI_COMPARE", "0")

    with patch(
        "app.services.post_batch_service._run_triage",
        return_value={"skipped": 0, "priority": 0, "review": 0, "top10": []},
    ):
        summary = run_post_batch()

    assert "triage" in summary
