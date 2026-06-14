"""Post scrape_batch hooks: triage, Pi compare, metadata sync."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

from app.config import Settings, get_settings
from app.services.inbox_service import InboxService

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def _run_triage(settings: Settings) -> dict:
    return InboxService(settings).run_triage()


def _run_pi_compare() -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "compare_remote_offers.py"),
        "--delta",
        "--sync-pi-metadata",
    ]
    if os.environ.get("POST_BATCH_IMPORT_GAPS") == "1":
        cmd.append("--import-pi-gaps")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        summary = {
            "returncode": result.returncode,
            "stdout": result.stdout[-2000:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        }
        if result.returncode != 0:
            logger.warning("Pi compare failed: %s", result.stderr)
        return summary
    except OSError as exc:
        logger.warning("Pi compare skipped: %s", exc)
        return {"error": str(exc)}


def run_post_batch(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    summary: dict = {}

    if os.environ.get("POST_BATCH_AUTO_TRIAGE", "1") != "0":
        triage = _run_triage(settings)
        summary["triage"] = triage
        logger.info(
            "Post-batch triage: priority=%s review=%s skipped=%s",
            triage.get("priority"),
            triage.get("review"),
            triage.get("skipped"),
        )

    if os.environ.get("POST_BATCH_PI_COMPARE", "1") != "0":
        summary["pi_compare"] = _run_pi_compare()

    return summary


async def run_post_batch_async(
    settings: Settings | None = None,
    on_progress=None,
) -> dict:
    """Async-safe post-batch hooks (triage + Pi compare)."""
    settings = settings or get_settings()
    summary: dict = {}
    loop = asyncio.get_running_loop()

    if os.environ.get("POST_BATCH_AUTO_TRIAGE", "1") != "0":
        if on_progress:
            await on_progress("post_batch", 99, "Triage inbox…")
        triage = await loop.run_in_executor(None, _run_triage, settings)
        summary["triage"] = triage
        logger.info(
            "Post-batch triage: priority=%s review=%s skipped=%s",
            triage.get("priority"),
            triage.get("review"),
            triage.get("skipped"),
        )

    if os.environ.get("POST_BATCH_PI_COMPARE", "1") != "0":
        if on_progress:
            await on_progress("post_batch", 99, "Porównanie z Pi…")
        summary["pi_compare"] = await loop.run_in_executor(None, _run_pi_compare)

    return summary
