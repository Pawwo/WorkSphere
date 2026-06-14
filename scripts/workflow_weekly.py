#!/usr/bin/env python3
"""
Cotygodniowy workflow: batch scrape (8 ról × portale) + triaż nowych ofert.

Użycie:
  cd WorkSphere
  source .venv/bin/activate
  python3 scripts/workflow_weekly.py

Opcje env:
  WORKFLOW_BROAD=1       — 8 portali (domyślnie)
  WORKFLOW_LIMIT=30      — limit na portal
  WORKFLOW_DAYS=7        — wiek ofert na portalu
  WORKFLOW_SKIP_SCRAPE=1 — tylko triaż (bez nowego scrape)
  WORKFLOW_SKIP_SLOW=1   — pomiń linkedin (tier 3)
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.jobs import ScrapeBatchRequest
from app.services.scrape_service import ScrapeService


async def run_scrape() -> dict:
    broad = os.environ.get("WORKFLOW_BROAD", "1") == "1"
    if os.environ.get("WORKFLOW_SKIP_SLOW") == "1":
        broad = False
    req = ScrapeBatchRequest(
        broad=broad,
        limit=int(os.environ.get("WORKFLOW_LIMIT", "30")),
        days=int(os.environ.get("WORKFLOW_DAYS", "7")),
    )
    print("=== Batch scrape ===")
    result = await ScrapeService().run_batch(req)
    summary = {
        "queries_run": result.queries_run,
        "new_count": result.new_count,
        "total_found": result.total_found,
    }
    print(json.dumps(summary, indent=2))
    return summary


def run_triage() -> None:
    print("\n=== Triage ===")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "workflow_triage.py")], check=True)


def run_pi_compare() -> None:
    if os.environ.get("WORKFLOW_SKIP_PI_COMPARE") == "1":
        return
    print("\n=== Pi coverage compare ===")
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "compare_remote_offers.py"), "--delta", "--sync-pi-metadata"],
        check=False,
    )


async def main() -> None:
    if os.environ.get("WORKFLOW_SKIP_SCRAPE") != "1":
        await run_scrape()
    run_triage()
    run_pi_compare()
    print("\n=== Następne kroki ===")
    print("1. python3 scripts/workflow_evaluate.py   # ocena top 10")
    print("2. python3 scripts/workflow_apply.py        # apply top 3")
    print("3. Dashboard: http://127.0.0.1:8080/dashboard")


if __name__ == "__main__":
    asyncio.run(main())
