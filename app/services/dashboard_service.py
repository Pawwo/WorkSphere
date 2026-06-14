from __future__ import annotations

import json
from typing import Optional

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.scrapers.bun_cli import BunCLIWrapper
from app.search.searxng_client import SearXNGClient
from app.services.profile_service import ProfileService
from app.storage.db import Database
from app.storage.files import load_seen_jobs


class DashboardService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.db = Database(self.settings.db_path)
        self.profile = ProfileService(self.settings)

    async def summary(self) -> dict:
        health = {
            "llm": await BielikClient(self.settings).healthcheck_extended(),
            "searxng": await SearXNGClient(self.settings).healthcheck(),
            "scrapers": await BunCLIWrapper(self.settings).healthcheck(),
        }
        profile_status = self.profile.get_status()
        seen = load_seen_jobs(self.settings.seen_jobs_path)
        new_jobs = sum(1 for v in seen.values() if v.status == "new")

        scrape_runs = await self.db.list_scrape_runs(5)
        apply_runs = await self.db.list_apply_runs(5)

        last_scrape_portal_summary = None
        last_scrape_portal_metrics = None
        if scrape_runs:
            latest = scrape_runs[0]
            raw_status = latest.get("portal_status")
            if raw_status:
                try:
                    status_data = json.loads(raw_status)
                    ok_count = len(status_data.get("ok", []))
                    err_count = len(status_data.get("errors", []))
                    last_scrape_portal_summary = f"{ok_count} OK / {ok_count + err_count} portali"
                    last_scrape_portal_metrics = status_data.get("portals")
                except json.JSONDecodeError:
                    last_scrape_portal_summary = None

        coverage_path = self.settings.data_dir / "comparison_cache" / "coverage_summary.json"
        pi_coverage = None
        if coverage_path.exists():
            try:
                pi_coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pi_coverage = None

        overall = "ok"
        llm_h = health["llm"]
        if (
            not llm_h.get("ok")
            or llm_h.get("inference_ok") is False
            or not health["searxng"].get("ok")
        ):
            overall = "degraded"
        if not health["scrapers"].get("ok"):
            overall = "degraded"

        return {
            "status": overall,
            "health": health,
            "profile": profile_status,
            "seen_jobs_total": len(seen),
            "seen_jobs_new": new_jobs,
            "last_scrape_portal_summary": last_scrape_portal_summary,
            "last_scrape_portal_metrics": last_scrape_portal_metrics,
            "pi_coverage": pi_coverage,
            "recent_scrapes": scrape_runs,
            "recent_applies": apply_runs,
            "quick_links": {
                "setup": "/setup",
                "scrape": "/scrape",
                "jobs": "/jobs",
                "apply": "/apply",
                "tools": "/tools",
                "docs": "/docs",
            },
        }
