"""Staged apply pipeline with checkpoints and application records."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, List, Optional

from app.config import Settings, get_settings
from app.models.apply import ApplyRequest, ApplyResponse, FitEvaluation, JobParsed, ReviewerResult
from app.models.jobs import SeenJobUpdate
from app.models.pipeline import PIPELINE_STAGES, STAGE_PROGRESS
from app.llm.client import BielikClient
from app.services.apply_service import ApplyService, slugify
from app.services.llm_power_service import LlmPowerService
from app.services.pipeline.apply_queue import llm_pipeline_slot
from app.services.pipeline.context import PipelineContext
from app.services.pipeline.stages import PipelineStages
from app.services.job_fetcher import fetch_job_posting
from app.services.jobs_service import JobsService
from app.storage.db import Database

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable]

_llm_warm_monotonic: float = 0.0


class PipelineService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.apply = ApplyService(self.settings)
        self.db = Database(self.settings.db_path)
        self.stages = PipelineStages(self)

    def _app_dir_path(self, company_slug: str) -> Path:
        return self.settings.data_dir / "applications" / company_slug

    def _save_json(self, ctx: PipelineContext, filename: str, data: Any) -> None:
        if not ctx.application_dir:
            return
        path = self.settings.repo_root / ctx.application_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_manifest(self, ctx: PipelineContext, stage: str, status: str) -> None:
        manifest = {
            "application_id": ctx.application_id,
            "run_id": ctx.run_id,
            "task_id": ctx.task_id,
            "company": ctx.parsed.company if ctx.parsed else "",
            "role": ctx.parsed.role if ctx.parsed else "",
            "url": ctx.request.url,
            "pipeline_stage": stage,
            "pipeline_status": status,
            "files": ctx.files,
            "pdf_files": ctx.pdf_files,
        }
        self._save_json(ctx, "manifest.json", manifest)

    async def _log(self, ctx: PipelineContext, body: str, *, kind: str = "stage_log") -> None:
        await self.db.add_application_activity(ctx.application_id, kind=kind, body=body)

    async def _set_stage(
        self,
        ctx: PipelineContext,
        stage: str,
        status: str,
        *,
        extra: Optional[dict] = None,
    ) -> None:
        if status == "running":
            ctx._stage_started[stage] = time.monotonic()
        elif status in ("done", "waiting", "failed") and stage in ctx._stage_started:
            elapsed_ms = int((time.monotonic() - ctx._stage_started[stage]) * 1000)
            ctx.stage_timings[stage] = elapsed_ms
            await self._log(ctx, f"{stage}: ukończono ({elapsed_ms} ms)")
            del ctx._stage_started[stage]
        fields: dict[str, Any] = {"pipeline_stage": stage, "pipeline_status": status}
        if extra:
            fields.update(extra)
        await self.db.update_application(ctx.application_id, **fields)
        self._save_manifest(ctx, stage, status)

    async def _wake_llm(self) -> dict:
        """Wake local GPU and wait until Bielik models + probe are ready."""
        global _llm_warm_monotonic
        cache_sec = max(30, int(getattr(self.settings, "pipeline_llm_warm_cache_seconds", 300) or 300))
        if time.monotonic() - _llm_warm_monotonic < cache_sec:
            client = BielikClient(self.settings)
            hc = await client.healthcheck_extended(force_probe=False)
            if hc.get("ok") and hc.get("inference_ok") is not False:
                logger.debug("LLM warm cache hit — skipping wake")
                return hc
        power = LlmPowerService(self.settings)
        if not power.enabled:
            client = BielikClient(self.settings)
            hc = await client.wait_until_ready(probe=True, force_probe=True)
            if hc.get("ok"):
                _llm_warm_monotonic = time.monotonic()
                logger.info("LLM ready at %s", self.settings.llm_base_url)
            else:
                logger.warning("LLM not ready: %s", hc.get("error") or hc.get("status"))
            return hc
        hc = await power.wake_and_prepare()
        if hc.get("ok"):
            _llm_warm_monotonic = time.monotonic()
            logger.info("LLM wake+probe OK (%s)", self.settings.llm_wake_url)
        else:
            logger.warning(
                "LLM wake+probe failed (%s): %s",
                self.settings.llm_wake_url,
                hc.get("error") or hc.get("status"),
            )
        return hc

    async def _ensure_llm_health(self, ctx: PipelineContext) -> dict:
        if ctx.llm_health is not None and ctx.llm_health.get("ok") and ctx.llm_health.get("inference_ok"):
            return ctx.llm_health
        hc = await self._wake_llm()
        if not hc.get("ok"):
            client = BielikClient(self.settings)
            hc = await client.wait_until_ready(probe=True, force_probe=True)
        ctx.llm_health = hc
        self.apply._llm_health = hc
        return hc

    async def _emit(
        self,
        cb: ProgressCallback,
        stage: str,
        message: str,
        *,
        progress: int | None = None,
    ) -> None:
        if cb:
            pct = progress if progress is not None else STAGE_PROGRESS.get(stage, 0)
            result = cb(stage, pct, message)
            if hasattr(result, "__await__"):
                await result

    async def create_application(self, request: ApplyRequest, task_id: Optional[str] = None) -> PipelineContext:
        bundle = self.apply._read_profile_bundle()
        run_id = await self.db.create_apply_run(
            company=None,
            role=None,
            url=request.url,
            stage="started",
            status="running",
        )
        existing = await self.db.get_application_by_url(request.url) if request.url else None
        if existing:
            app_id = existing["id"]
            await self.db.update_application(
                app_id,
                run_id=run_id,
                task_id=task_id,
                pipeline_stage="parse",
                pipeline_status="running",
                hiring_stage="draft",
                cv_file=None,
                cover_file=None,
                pdf_cv=None,
                pdf_cover=None,
                interview_prep_file=None,
                verification_pass=None,
                reviewer_verdict=None,
            )
            log_msg = "Wznowiono istniejącą aplikację dla tego URL"
        else:
            app_id = await self.db.create_application(
                company="—",
                role="—",
                url=request.url,
                run_id=run_id,
                task_id=task_id,
                pipeline_stage="parse",
                pipeline_status="running",
            )
            log_msg = "Utworzono aplikację"
        ctx = PipelineContext(
            request=request,
            application_id=app_id,
            run_id=run_id,
            task_id=task_id,
            bundle=bundle,
        )
        await self._log(ctx, log_msg)
        return ctx

    def to_response(self, ctx: PipelineContext) -> ApplyResponse:
        msg = "Ocena gotowa. Wyślij proceed=true aby wygenerować CV i list."
        if ctx.request.proceed and ctx.verification:
            msg = (
                "Aplikacja gotowa. Sprawdź checklistę weryfikacji i pliki PDF przed wysłaniem."
                if ctx.verification.get("all_pass")
                else "Aplikacja wygenerowana — niektóre punkty weryfikacji wymagają uwagi."
            )
        stage = "evaluated" if not ctx.request.proceed else "completed"
        return ApplyResponse(
            run_id=ctx.run_id,
            stage=stage,
            parsed=ctx.parsed,
            evaluation=ctx.evaluation,
            reviewer=ctx.reviewer,
            files=ctx.files,
            pdf_files=ctx.pdf_files,
            warnings=ctx.warnings,
            verification=ctx.verification,
            pdf_verification=ctx.pdf_verification,
            interview_prep_file=ctx.interview_prep_file,
            tailoring_decisions=ctx.tailoring_decisions,
            message=msg,
        )

    async def run_sync(self, request: ApplyRequest) -> ApplyResponse:
        await self._wake_llm()
        ctx = await self.create_application(request)
        await self._ensure_llm_health(ctx)
        await self.stages.stage_parse(ctx)
        await self.stages.stage_evaluate(ctx)
        if not await self.stages.stage_proceed_gate(ctx):
            return self.to_response(ctx)
        await self._run_llm_stages(ctx)
        return self.to_response(ctx)

    async def run_async(
        self,
        request: ApplyRequest,
        task_id: str,
        on_progress: ProgressCallback,
        *,
        ctx: Optional[PipelineContext] = None,
    ) -> dict:
        await self._emit(on_progress, "parse", "Budzenie LLM…", progress=5)
        await self._wake_llm()
        if ctx is None:
            ctx = await self.create_application(request, task_id=task_id)
        await self._ensure_llm_health(ctx)
        await self.db.update_application(ctx.application_id, task_id=task_id)
        try:
            await self.stages.stage_parse(ctx, on_progress)
            await self.stages.stage_evaluate(ctx, on_progress)
            if not await self.stages.stage_proceed_gate(ctx, on_progress):
                return {
                    "application_id": ctx.application_id,
                    "run_id": ctx.run_id,
                    "stage": "proceed",
                    "status": "waiting",
                }
            await self._run_post_proceed(ctx, on_progress)
            resp = self.to_response(ctx)
            return {
                "application_id": ctx.application_id,
                "run_id": ctx.run_id,
                "stage": "done",
                "status": "completed",
                "response": resp.model_dump(),
            }
        except Exception as exc:
            await self.db.update_application(
                ctx.application_id,
                pipeline_status="failed",
            )
            await self._log(ctx, f"Błąd: {exc}")
            raise

    async def _run_llm_stages(self, ctx: PipelineContext, on_progress: ProgressCallback = None) -> None:
        async def on_waiting(position: int) -> None:
            msg = f"Kolejka LLM (pozycja {position})"
            await self._emit(on_progress, "draft", msg)
            if ctx.application_id:
                await self._log(ctx, msg)

        async with llm_pipeline_slot(on_waiting=on_waiting):
            await self.stages.stage_draft(ctx, on_progress)
            await self.stages.stage_review(ctx, on_progress)
        await self.stages.stage_pdf(ctx, on_progress)
        await self.stages.stage_checklist(ctx, on_progress)
        await self.stages.stage_interview_prep(ctx, on_progress)
        await self.stages.stage_tracker(ctx, on_progress)
        await self.stages._finalize(ctx)

    async def _run_post_proceed(self, ctx: PipelineContext, on_progress: ProgressCallback) -> None:
        await self._run_llm_stages(ctx, on_progress)

    async def proceed(
        self,
        application_id: int,
        *,
        compile_pdf: bool = True,
        on_progress: ProgressCallback = None,
    ) -> ApplyResponse:
        row = await self.db.get_application(application_id)
        if not row:
            raise ValueError("Application not found")
        if row.get("pipeline_stage") not in ("proceed", "evaluate") and row.get("pipeline_status") != "waiting":
            if row.get("pipeline_stage") == "done":
                raise ValueError("Application already completed")
        run = await self.db.get_apply_run(row["run_id"])
        result = json.loads(run["result_json"]) if run and run.get("result_json") else {}
        parsed_data = result.get("parsed") or self._load_stage_json(row, "parsed.json")
        eval_data = result.get("evaluation") or self._load_stage_json(row, "evaluation.json")
        if not parsed_data:
            raise ValueError("Brak danych parse — uruchom pipeline od początku")
        ctx = PipelineContext(
            request=ApplyRequest(
                url=row.get("url"),
                proceed=True,
                compile_pdf=compile_pdf,
            ),
            application_id=application_id,
            run_id=row["run_id"],
            task_id=row.get("task_id"),
            company_slug=row.get("company_slug") or "",
            application_dir=row.get("application_dir") or "",
            parsed=JobParsed(**parsed_data),
            evaluation=FitEvaluation(**eval_data) if eval_data else None,
            bundle=self.apply._read_profile_bundle(),
        )
        if ctx.parsed:
            ctx.role_slug = slugify(ctx.parsed.role)
        await self._emit(on_progress, "parse", "Budzenie LLM…", progress=5)
        await self._wake_llm()
        await self._ensure_llm_health(ctx)
        await self._set_stage(ctx, "proceed", "done")
        await self._run_post_proceed(ctx, on_progress)
        return self.to_response(ctx)

    def _load_stage_json(self, row: dict, filename: str) -> dict:
        app_dir = row.get("application_dir")
        if not app_dir:
            return {}
        path = self.settings.repo_root / app_dir / filename
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    async def retry_stage(self, application_id: int, stage: str, *, compile_pdf: bool = True) -> ApplyResponse:
        row = await self.db.get_application(application_id)
        if not row:
            raise ValueError("Application not found")
        run = await self.db.get_apply_run(row["run_id"])
        result = json.loads(run["result_json"]) if run and run.get("result_json") else {}
        parsed_data = result.get("parsed") or self._load_stage_json(row, "parsed.json")

        # Parse retry should be able to run from URL even if previous parse never produced parsed.json.
        if stage == "parse":
            url = row.get("url")
            if not url:
                raise ValueError("Brak URL — parse retry wymaga url w aplikacji")
            ctx = PipelineContext(
                request=ApplyRequest(url=url, proceed=False, compile_pdf=compile_pdf),
                application_id=application_id,
                run_id=row["run_id"],
                task_id=row.get("task_id"),
                bundle=self.apply._read_profile_bundle(),
            )
        else:
            if not parsed_data:
                raise ValueError("Brak parsed.json")
            ctx = PipelineContext(
                request=ApplyRequest(url=row.get("url"), proceed=True, compile_pdf=compile_pdf),
                application_id=application_id,
                run_id=row["run_id"],
                company_slug=row.get("company_slug") or slugify(parsed_data.get("company", "")),
                role_slug=slugify(parsed_data.get("role", "")),
                application_dir=row.get("application_dir") or "",
                parsed=JobParsed(**parsed_data),
                evaluation=FitEvaluation(**result["evaluation"]) if result.get("evaluation") else None,
                bundle=self.apply._read_profile_bundle(),
            )
        reviewer_data = self._load_stage_json(row, "reviewer.json")
        if reviewer_data:
            ctx.reviewer = ReviewerResult(**reviewer_data)

        await self._wake_llm()
        await self._ensure_llm_health(ctx)

        eval_data = result.get("evaluation") or self._load_stage_json(row, "evaluation.json")
        if eval_data:
            ctx.evaluation = FitEvaluation(**eval_data)

        if stage == "parse":
            await self.stages.stage_parse(ctx)
            await self.stages.stage_evaluate(ctx)
            await self.stages.stage_proceed_gate(ctx)
            result = {
                "parsed": ctx.parsed.model_dump() if ctx.parsed else {},
                "evaluation": ctx.evaluation.model_dump() if ctx.evaluation else {},
            }
            await self.db.update_apply_run(
                ctx.run_id,
                stage="evaluated",
                status="completed",
                result_json=json.dumps(result, ensure_ascii=False),
            )
        elif stage == "evaluate":
            await self.stages.stage_evaluate(ctx)
            await self.stages._finalize(ctx)
        elif stage == "draft":
            await self._run_post_proceed(ctx, None)
        elif stage == "pdf":
            if not hasattr(ctx, "_cv_tex"):
                cv_file = row.get("cv_file")
                cover_file = row.get("cover_file")
                if cv_file and cover_file:
                    ctx._cv_tex = (self.settings.repo_root / cv_file).read_text(encoding="utf-8")
                    ctx._cover_tex = (self.settings.repo_root / cover_file).read_text(encoding="utf-8")
                    ctx.files = [cv_file, cover_file]
                else:
                    raise ValueError("Brak plików draft — uruchom draft najpierw")
            await self.stages.stage_pdf(ctx)
            await self.stages.stage_checklist(ctx)
            await self.stages._finalize(ctx)
        elif stage == "checklist":
            cv_file = row.get("cv_file")
            cover_file = row.get("cover_file")
            if cv_file and cover_file:
                ctx._cv_tex = (self.settings.repo_root / cv_file).read_text(encoding="utf-8")
                ctx._cover_tex = (self.settings.repo_root / cover_file).read_text(encoding="utf-8")
            ctx.pdf_files = [row["pdf_cv"], row["pdf_cover"]] if row.get("pdf_cv") else []
            await self.stages.stage_checklist(ctx)
            await self.stages._finalize(ctx)
        elif stage == "interview_prep":
            await self.stages.stage_interview_prep(ctx)
            await self.stages._finalize(ctx)
        else:
            raise ValueError(f"Retry not supported for stage: {stage}")
        return self.to_response(ctx)
