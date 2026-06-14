#!/usr/bin/env python3
"""Re-audit auto-triage skipped jobs: refetch posting, re-assess salary, restore false negatives.

Usage:
  uv run python scripts/retriage_auto_skipped.py --dry-run
  uv run python scripts/retriage_auto_skipped.py --limit 50
  uv run python scripts/retriage_auto_skipped.py --category auto_low_fit
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services.inbox.auto_skip_reaudit import reaudit_auto_skipped_jobs  # noqa: E402
from app.services.inbox_service import InboxService  # noqa: E402


def _print_summary(result: dict) -> None:
    print(f"Candidates (auto_triage skipped): {result['candidates']}")
    print(f"Would restore to inbox: {result['restored']}")
    print(f"Still skipped after re-audit: {result['still_skipped']}")
    print(f"HTTP fetch OK: {result['fetch_ok']} | Errors: {result['errors']}")
    if result.get("dry_run"):
        print("\n(dry-run — no changes written)")

    restored_rows = [r for r in result["rows"] if r.get("would_restore")]
    if restored_rows:
        print("\nRestore queue:")
        for r in restored_rows[:30]:
            print(
                f"  [{r['old_triage_score']}→{r['new_triage_score']}] "
                f"{r['old_fit']}→{r['new_fit']} tier={r['new_tier']} | "
                f"salary {r['salary_before']}→{r['salary_after']} "
                f"({r['salary_source_after']}) | {r['title'][:45]} @ {r['company'][:20]}"
            )
        if len(restored_rows) > 30:
            print(f"  … and {len(restored_rows) - 30} more")

    salary_fixes = [
        r
        for r in result["rows"]
        if not r.get("would_restore")
        and r.get("salary_meets_before") is False
        and r.get("salary_meets_after") is True
    ]
    if salary_fixes:
        print(f"\nSalary fixed but still skipped (e.g. language): {len(salary_fixes)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze only; do not update seen_jobs or run triage",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max jobs to process")
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Only auto skip category (repeatable), e.g. auto_low_fit",
    )
    parser.add_argument(
        "--no-triage",
        action="store_true",
        help="Skip final run_triage() after restoring jobs",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write JSON report path (default: data/job_scraper/reaudit_auto_skipped_<ts>.json)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    settings = get_settings()
    categories = set(args.categories) if args.categories else None

    print("Re-auditing auto-triage skipped jobs…")
    result = reaudit_auto_skipped_jobs(
        settings=settings,
        dry_run=args.dry_run,
        limit=args.limit,
        categories=categories,
    )
    _print_summary(result)

    if not args.dry_run and result["restored"] and not args.no_triage:
        print("\nRunning inbox triage to refresh tiers…")
        triage = InboxService(settings).run_triage()
        result["triage"] = {
            "priority": triage.get("priority"),
            "review": triage.get("review"),
            "skipped": triage.get("skipped"),
        }
        print(
            f"Triage — priority: {triage.get('priority')}, "
            f"review: {triage.get('review')}, auto-skipped: {triage.get('skipped')}"
        )

    report_path = args.report
    if report_path is None and not args.dry_run:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = settings.job_scraper_dir / f"reaudit_auto_skipped_{ts}.json"
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nReport: {report_path}")


if __name__ == "__main__":
    main()
