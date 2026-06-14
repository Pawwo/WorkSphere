"""CRUD for applications table."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.config import Settings, get_settings
from app.models.applications import ApplicationRecord
from app.storage.db import Database
from app.storage.job_repository import JobRepository, job_url_lookup_variants


class ApplicationService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.db = Database(self.settings.db_path)

    async def get(self, app_id: int) -> Optional[ApplicationRecord]:
        row = await self.db.get_application(app_id)
        if not row:
            return None
        activities = await self.db.list_application_activities(app_id)
        manifest = self._load_manifest(row.get("application_dir"))
        result = await self._load_run_result(row.get("run_id"))
        app_dir = row.get("application_dir")
        if app_dir:
            if not result.get("parsed"):
                parsed = self.load_stage_json(app_dir, "parsed.json")
                if parsed:
                    result["parsed"] = parsed
            if not result.get("evaluation"):
                evaluation = self.load_stage_json(app_dir, "evaluation.json")
                if evaluation:
                    result["evaluation"] = evaluation
            if not result.get("reviewer"):
                reviewer = self.load_stage_json(app_dir, "reviewer.json")
                if reviewer:
                    result["reviewer"] = reviewer
            if not result.get("verification"):
                verification = self.load_stage_json(app_dir, "verification.json")
                if verification:
                    result["verification"] = verification
            if not result.get("draft"):
                draft = self.load_stage_json(app_dir, "draft.json")
                if draft:
                    result["draft"] = draft
        inbox_context = self._load_inbox_context(row.get("url"))
        return ApplicationRecord(
            **row,
            activities=activities,
            manifest=manifest,
            result=result,
            inbox_context=inbox_context,
        )

    async def list(
        self,
        *,
        hiring_stage: Optional[str] = None,
        pipeline_stage: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        return await self.db.list_applications(
            hiring_stage=hiring_stage,
            pipeline_stage=pipeline_stage,
            limit=limit,
        )

    async def update(self, app_id: int, **fields) -> bool:
        row = await self.db.get_application(app_id)
        if not row:
            return False
        prev_stage = row.get("hiring_stage")
        await self.db.update_application(app_id, **fields)
        new_stage = fields.get("hiring_stage", prev_stage)
        if new_stage == "interview" and prev_stage != "interview":
            import asyncio

            asyncio.create_task(self._auto_interview_prep_background(app_id))
        return True

    async def _auto_interview_prep_background(self, app_id: int) -> None:
        import logging

        from app.services.pipeline_service import PipelineService

        logger = logging.getLogger(__name__)
        if not self.settings.pipeline_interview_prep_enabled:
            return
        row = await self.db.get_application(app_id)
        if not row or row.get("hiring_stage") != "interview":
            return
        if row.get("interview_prep_file"):
            return
        try:
            await PipelineService(self.settings).retry_stage(app_id, "interview_prep")
        except Exception as exc:
            logger.warning("auto interview prep failed for app %s: %s", app_id, exc)

    async def add_activity(
        self,
        app_id: int,
        *,
        kind: str,
        body: str,
        author: str = "system",
    ) -> None:
        await self.db.add_application_activity(app_id, kind=kind, body=body, author=author)

    def _load_manifest(self, application_dir: Optional[str]) -> dict:
        if not application_dir:
            return {}
        path = self.settings.repo_root / application_dir / "manifest.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    async def _load_run_result(self, run_id: Optional[int]) -> dict:
        if not run_id:
            return {}
        row = await self.db.get_apply_run(run_id)
        if not row or not row.get("result_json"):
            return {}
        try:
            return json.loads(row["result_json"])
        except json.JSONDecodeError:
            return {}

    def load_stage_json(self, application_dir: str, name: str) -> dict:
        path = self.settings.repo_root / application_dir / name
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _load_inbox_context(self, url: Optional[str]) -> dict:
        if not url:
            return {}
        ctx: dict = {}
        found = JobRepository(self.settings.seen_jobs_path).get_by_url(url)
        if found:
            _, job = found
            ctx = {
                "fit": job.fit,
                "portal": job.portal,
                "location": job.location,
                "pi_score": job.pi_score,
                "pi_verdict": job.pi_verdict,
                "pi_app": job.pi_app,
                "salary_b2b_monthly": job.salary_b2b_monthly,
                "salary_meets_threshold": job.salary_meets_threshold,
                "first_seen": job.first_seen,
            }
        triage_path = self.settings.job_scraper_dir / "triage_result.json"
        if triage_path.exists():
            try:
                triage = json.loads(triage_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                triage = {}
            for item in triage.get("ranked", triage.get("jobs", [])):
                item_url = item.get("url", "")
                for candidate in job_url_lookup_variants(url):
                    if item_url == candidate or item_url == url:
                        ctx.update(
                            {
                                "tier": item.get("tier"),
                                "triage_score": item.get("triage_score"),
                                "triage_reason": item.get("triage_reason"),
                                "quick_fit": item.get("quick_fit") or ctx.get("fit"),
                            }
                        )
                        break
        return ctx
