"""Post scrape_batch hooks: triage."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from app.config import Settings, get_settings
from app.services.inbox_service import InboxService

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def _run_triage(settings: Settings, triage_keys: set[str] | None = None) -> dict:
    keys = triage_keys
    if keys and os.environ.get("POST_BATCH_TRIAGE_SCOPE", "incremental") == "full":
        keys = None
    return InboxService(settings).run_triage(keys=keys)


def run_post_batch(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    summary: dict = {}

    if os.environ.get("POST_BATCH_AUTO_TRIAGE", "1") != "0":
        triage = _run_triage(settings, None)
        summary["triage"] = triage
        logger.info(
            "Post-batch triage: priority=%s review=%s skipped=%s",
            triage.get("priority"),
            triage.get("review"),
            triage.get("skipped"),
        )

    return summary


async def run_post_batch_async(
    settings: Settings | None = None,
    on_progress=None,
    triage_keys: set[str] | None = None,
) -> dict:
    """Async-safe post-batch hooks (triage)."""
    settings = settings or get_settings()
    summary: dict = {}
    loop = asyncio.get_running_loop()

    if os.environ.get("POST_BATCH_AUTO_TRIAGE", "1") != "0":
        if on_progress:
            await on_progress("post_batch", 99, "Triage inbox…")
        triage = await loop.run_in_executor(None, _run_triage, settings, triage_keys)
        summary["triage"] = triage
        logger.info(
            "Post-batch triage: priority=%s review=%s skipped=%s",
            triage.get("priority"),
            triage.get("review"),
            triage.get("skipped"),
        )

    return summary
