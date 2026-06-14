#!/usr/bin/env python3
"""Migrate job_search_tracker.csv rows into SQLite applications table."""

from __future__ import annotations

import asyncio
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.services.apply_service import slugify
from app.storage.db import Database


async def migrate() -> int:
    settings = get_settings()
    csv_path = settings.tracker_path
    db = Database(settings.db_path)
    if not csv_path.exists():
        print("No tracker CSV found — nothing to migrate.")
        return 0

    migrated = 0
    seen_urls: set[str] = set()

    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            company = (row.get("company") or "").strip()
            role = (row.get("role") or row.get("role_type") or "").strip()
            url = (row.get("url") or row.get("source") or "").strip()
            if not company or company == "—":
                continue
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
                existing = await db.get_application_by_url(url)
                if existing:
                    continue

            hiring = (row.get("status") or "applied").strip().lower()
            if hiring not in (
                "draft",
                "applied",
                "screening",
                "interview",
                "offer",
                "rejected",
                "archived",
            ):
                hiring = "applied"

            slug = slugify(company)
            app_dir = str((settings.data_dir / "applications" / slug).relative_to(settings.repo_root))

            app_id = await db.create_application(
                company=company,
                role=role or "—",
                url=url or None,
                company_slug=slug,
                pipeline_stage="done",
                pipeline_status="done",
                hiring_stage=hiring,
                application_dir=app_dir,
                run_id=None,
                task_id=None,
            )
            await db.update_application(
                app_id,
                fit_score=row.get("fit_score") or row.get("fit_rating"),
                overall_fit=row.get("fit_score") or row.get("fit_rating"),
                cv_file=row.get("cv_file"),
                cover_file=row.get("cover_file") or row.get("cover_letter_file"),
                notes=(row.get("notes") or "")[:500],
            )
            migrated += 1

    print(f"Migrated {migrated} tracker rows to applications table.")
    return migrated


if __name__ == "__main__":
    asyncio.run(migrate())
