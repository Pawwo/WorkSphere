#!/usr/bin/env python3
"""Triaż seen_jobs.json pod profil COO / Operations / Odoo / AI transformation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.workflow_service import WorkflowService  # noqa: E402


def main() -> None:
    result = WorkflowService().run_triage()
    print(f"Skipped: {result['skipped']}")
    print(f"Priority: {result['priority']}, Review: {result['review']}")
    print("\nTop 10 evaluate queue:")
    for i, r in enumerate(result["top10"], 1):
        print(f"  {i}. [{r['triage_score']}] {r['title'][:55]} | {r['company'][:25]}")


if __name__ == "__main__":
    main()
