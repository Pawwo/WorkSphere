"""Pipeline stage implementations."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Callable, Optional

from app.models.jobs import SeenJobUpdate
from app.services.jobs_service import JobsService
from app.services.job_fetcher import fetch_job_posting, _linkedin_body_usable
from app.services.inbox.manual_import import import_manual_job
from app.services.apply_service import (
    application_cover_filename,
    application_cv_filename,
    slugify,
)
from app.services.cv.html_builder import build_cover_html, build_cv_html
from app.services.cv.language import localize_identity
from app.services.cv.renderer_factory import get_document_renderer, get_pdf_compiler

from app.services.pipeline.context import PipelineContext

if TYPE_CHECKING:
    from app.services.pipeline_service import PipelineService

ProgressCallback = Optional[Callable]


class PipelineStages:
    """Stage methods extracted from PipelineService."""

    def __init__(self, svc: "PipelineService"):
        self.svc = svc

    async def stage_parse(self, ctx: PipelineContext, cb: ProgressCallback = None) -> None:
        await self.svc._emit(cb, "parse", "Parsowanie ogłoszenia…")
        await self.svc._set_stage(ctx, "parse", "running")
        ctx.parsed = await fetch_job_posting(url=ctx.request.url, text=ctx.request.text)
        import_result = await import_manual_job(url=ctx.request.url, parsed=ctx.parsed)
        ctx.inbox_imported = import_result
        if import_result.created:
            await self.svc._log(
                ctx,
                f"Inbox: dodano {import_result.company} — {import_result.title} (fit={import_result.fit})",
            )
        else:
            await self.svc._log(ctx, f"Inbox: oferta już w skrzynce ({import_result.title})")
        ctx.company_slug = slugify(ctx.parsed.company)
        ctx.role_slug = slugify(ctx.parsed.role)
        ctx.application_dir = str(
            (self.svc.settings.data_dir / "applications" / ctx.company_slug).relative_to(self.svc.settings.repo_root)
        )
        self.svc._app_dir_path(ctx.company_slug).mkdir(parents=True, exist_ok=True)
        self.svc._save_json(ctx, "parsed.json", ctx.parsed.model_dump())
        await self.svc.db.update_application(
            ctx.application_id,
            company=ctx.parsed.company,
            role=ctx.parsed.role,
            company_slug=ctx.company_slug,
            application_dir=ctx.application_dir,
        )
        await self.svc.db.update_apply_run(
            ctx.run_id,
            stage="parse",
            status="running",
            result_json=json.dumps({"parsed": ctx.parsed.model_dump()}, ensure_ascii=False),
        )
        await self.svc._log(ctx, f"Parse: {ctx.parsed.company} — {ctx.parsed.role}")
        if ctx.request.url and "linkedin" in ctx.request.url.lower():
            if not _linkedin_body_usable(ctx.parsed.raw_text or ""):
                await self.svc._log(
                    ctx,
                    "Parse: login wall LinkedIn — brak pełnego opisu ogłoszenia (chrome-only)",
                )
        await self.svc._set_stage(ctx, "parse", "done")

    async def stage_evaluate(self, ctx: PipelineContext, cb: ProgressCallback = None) -> None:
        await self.svc._emit(cb, "evaluate", "Ocena dopasowania…")
        await self.svc._set_stage(ctx, "evaluate", "running")
        ctx.evaluation = await self.svc.apply.evaluate(ctx.parsed, ctx.bundle)
        self.svc._save_json(ctx, "evaluation.json", ctx.evaluation.model_dump())
        await self.svc.db.update_application(
            ctx.application_id,
            overall_fit=ctx.evaluation.overall_fit,
            fit_score=ctx.evaluation.overall_fit,
            recommendation=ctx.evaluation.recommendation,
        )
        await self.svc.db.update_apply_run(
            ctx.run_id,
            stage="evaluated",
            status="running",
            result_json=json.dumps(
                {"parsed": ctx.parsed.model_dump(), "evaluation": ctx.evaluation.model_dump()},
                ensure_ascii=False,
            ),
        )
        await self.svc._log(ctx, f"Evaluate: fit={ctx.evaluation.overall_fit}")
        await self.svc._set_stage(ctx, "evaluate", "done")

    async def stage_proceed_gate(self, ctx: PipelineContext, cb: ProgressCallback = None) -> bool:
        """Returns True if should continue to draft."""
        if not ctx.request.proceed:
            await self.svc._emit(cb, "proceed", "Oczekiwanie na Proceed…")
            await self.svc._set_stage(ctx, "proceed", "waiting")
            await self.svc._log(ctx, "Oczekiwanie na potwierdzenie Proceed")
            return False
        await self.svc._set_stage(ctx, "proceed", "done")
        return True

    async def stage_draft(self, ctx: PipelineContext, cb: ProgressCallback = None) -> None:
        await self.svc._emit(cb, "draft", "Generowanie CV i listu…")
        await self.svc._set_stage(ctx, "draft", "running")
        await self.svc._ensure_llm_health(ctx)

        company = ctx.parsed.company if ctx.parsed else ""
        search_prefetch = asyncio.create_task(self.svc.apply.prefetch_company_search(company))

        async def on_draft_progress(message: str) -> None:
            await self.svc._log(ctx, message)
            await self.svc._emit(cb, "draft", message)

        try:
            cv_data, cover_data, tailoring = await self.svc.apply._draft_content(
                ctx.parsed,
                ctx.bundle,
                company_slug=ctx.company_slug,
                job_url=ctx.request.url,
                on_progress=on_draft_progress,
            )
        finally:
            await search_prefetch
        ctx.tailoring_decisions = tailoring
        ctx.job_targets = getattr(self.svc.apply, "_last_job_targets", {}) or {}
        if getattr(self.svc.apply, "_last_tailor_degraded", False):
            ctx.llm_json_broken = True
        profile_md = ctx.bundle.get("01-candidate-profile.md", "")
        identity = localize_identity(
            self.svc.apply._parse_identity(profile_md),
            ctx.parsed.language,
        )
        renderer = get_document_renderer(self.svc.settings)
        if renderer.file_extension == ".html":
            cv_tex = build_cv_html(
                cv_data,
                identity,
                ctx.company_slug,
                profile_md=profile_md,
                job_targets=ctx.job_targets,
                highlight_keywords=getattr(
                    self.svc.settings, "ats_bold_keywords_in_bullets", True
                ),
            )
            cover_tex = build_cover_html(cover_data, identity, ctx.company_slug, ctx.role_slug)
        else:
            cv_tex = renderer.render_cv(cv_data, identity, ctx.company_slug)
            cover_tex = renderer.render_cover(cover_data, identity, ctx.company_slug, ctx.role_slug)
        ctx._cv_tex = cv_tex
        ctx._cover_tex = cover_tex
        ctx._cv_data = cv_data
        ctx._cover_data = cover_data
        ctx._identity = identity
        await self.svc._log(ctx, "Draft: CV i list przygotowane")
        await self.svc._set_stage(ctx, "draft", "done")

    async def stage_review(self, ctx: PipelineContext, cb: ProgressCallback = None) -> None:
        await self.svc._emit(cb, "review", "Reviewer…")
        await self.svc._set_stage(ctx, "review", "running")
        ctx.reviewer = await self.svc.apply._review(
            ctx.parsed,
            ctx._cv_tex,
            ctx._cover_tex,
            ctx.bundle,
            skip_llm=ctx.llm_json_broken,
            llm_health=ctx.llm_health,
        )
        ctx._cv_tex = self.svc.apply._apply_edits(ctx._cv_tex, ctx.reviewer.structured_edits, "cv")
        ctx._cover_tex = self.svc.apply._apply_edits(ctx._cover_tex, ctx.reviewer.structured_edits, "cover")
        self.svc._save_json(ctx, "reviewer.json", ctx.reviewer.model_dump())
        await self.svc.db.update_application(
            ctx.application_id,
            reviewer_verdict=ctx.reviewer.overall_verdict,
        )
        await self.svc._log(ctx, f"Review: verdict={ctx.reviewer.overall_verdict}")
        await self.svc._set_stage(ctx, "review", "done")
        await self.stage_persist_tex(ctx, cb)

    async def stage_persist_tex(self, ctx: PipelineContext, cb: ProgressCallback = None) -> None:
        """Write CV/cover sources to disk after draft+review (upstream Step 2+4)."""
        if not getattr(ctx, "_cv_tex", None) or not getattr(ctx, "_cover_tex", None):
            return
        await self._write_draft_files(ctx)
        draft_meta = {
            "cv_file": ctx.files[0] if ctx.files else None,
            "cover_file": ctx.files[1] if len(ctx.files) > 1 else None,
            "tailoring_decisions": ctx.tailoring_decisions,
            "job_targets": ctx.job_targets,
        }
        self.svc._save_json(ctx, "draft.json", draft_meta)
        ext = get_document_renderer(self.svc.settings).file_extension
        await self.svc._log(ctx, f"Zapisano {ext}: {', '.join(ctx.files)}")

    def _application_filename_context(self, ctx: PipelineContext) -> tuple[str, str]:
        profile_md = ctx.bundle.get("01-candidate-profile.md", "")
        identity = self.svc.apply._parse_identity(profile_md)
        full_name = identity.get("name") or "Candidate"
        company = (ctx.parsed.company if ctx.parsed else "") or ctx.company_slug.replace("_", " ")
        return full_name, company

    async def _write_draft_files(self, ctx: PipelineContext) -> None:
        ext = get_document_renderer(self.svc.settings).file_extension
        full_name, company = self._application_filename_context(ctx)
        cv_name = application_cv_filename(full_name, company, ext)
        cover_name = application_cover_filename(full_name, company, ext)
        self.svc.apply.cv_dir.mkdir(parents=True, exist_ok=True)
        self.svc.apply.cover_dir.mkdir(parents=True, exist_ok=True)
        cv_path = self.svc.apply.cv_dir / cv_name
        cover_path = self.svc.apply.cover_dir / cover_name
        cv_path.write_text(ctx._cv_tex, encoding="utf-8")
        cover_path.write_text(ctx._cover_tex, encoding="utf-8")
        ctx.files = [
            str(cv_path.relative_to(self.svc.settings.repo_root)),
            str(cover_path.relative_to(self.svc.settings.repo_root)),
        ]
        await self.svc.db.update_application(
            ctx.application_id,
            cv_file=ctx.files[0] if ctx.files else None,
            cover_file=ctx.files[1] if len(ctx.files) > 1 else None,
        )

    async def stage_pdf(self, ctx: PipelineContext, cb: ProgressCallback = None) -> None:
        if not ctx.files:
            await self._write_draft_files(ctx)
        await self.svc._emit(cb, "pdf", "Kompilacja PDF…")
        await self.svc._set_stage(ctx, "pdf", "running")
        if ctx.request.compile_pdf and ctx.files:
            cv_path = self.svc.settings.repo_root / ctx.files[0]
            cover_path = self.svc.settings.repo_root / ctx.files[1]
            cv_name = cv_path.name
            cover_name = cover_path.name
            compiler = get_pdf_compiler(self.svc.settings)
            ctx.pdf_files, pdf_warnings, ctx.pdf_verification = await compiler.compile_and_verify(
                cv_path, cover_path, cv_name, cover_name
            )
            ctx.warnings.extend(pdf_warnings)
            pdf_cv = ctx.pdf_files[0] if ctx.pdf_files else None
            pdf_cover = ctx.pdf_files[1] if len(ctx.pdf_files) > 1 else None
            await self.svc.db.update_application(
                ctx.application_id,
                pdf_cv=pdf_cv,
                pdf_cover=pdf_cover,
            )
        else:
            await self.svc._log(ctx, "PDF: pominięto (compile_pdf=false lub brak plików)")
        await self.svc._set_stage(ctx, "pdf", "done")
        await self.svc._log(ctx, f"PDF: {', '.join(ctx.pdf_verification) or 'brak'}")

    async def stage_checklist(self, ctx: PipelineContext, cb: ProgressCallback = None) -> None:
        await self.svc._emit(cb, "checklist", "Checklist weryfikacji…")
        await self.svc._set_stage(ctx, "checklist", "running")
        from app.services.verification_service import run_verification_checklist, summarize_tailoring

        cv_tex = ctx._cv_tex
        cover_tex = ctx._cover_tex
        renderer = "html" if self.svc.settings.cv_renderer == "html" else "auto"
        if ctx.files and str(ctx.files[0]).endswith(".html"):
            renderer = "html"
        ctx.verification = run_verification_checklist(
            job=ctx.parsed,
            cv_tex=cv_tex,
            cover_tex=cover_tex,
            profile_md=ctx.bundle.get("01-candidate-profile.md", ""),
            evaluation=ctx.evaluation,
            reviewer=ctx.reviewer,
            pdf_files=ctx.pdf_files,
            pdf_checks=ctx.pdf_verification,
            renderer=renderer,
            job_targets=ctx.job_targets,
            tailoring_decisions=ctx.tailoring_decisions,
        )
        ctx.tailoring_decisions.extend(
            summarize_tailoring(ctx.parsed, ctx.reviewer, ctx.evaluation)
        )
        self.svc._save_json(ctx, "verification.json", ctx.verification)
        await self.svc.db.update_application(
            ctx.application_id,
            verification_pass=1 if ctx.verification.get("all_pass") else 0,
        )
        await self.svc._log(
            ctx,
            f"Checklist: {ctx.verification.get('passed', 0)}/{ctx.verification.get('total', 0)} passed",
        )
        await self.svc._set_stage(ctx, "checklist", "done")

    async def stage_interview_prep(self, ctx: PipelineContext, cb: ProgressCallback = None) -> None:
        if not getattr(self.svc.settings, "pipeline_interview_prep_enabled", False):
            await self.svc._log(ctx, "Interview prep: wyłączone (config)")
            await self.svc._set_stage(ctx, "interview_prep", "done")
            return
        row = await self.svc.db.get_application(ctx.application_id)
        hiring_stage = (row or {}).get("hiring_stage") or "draft"
        if hiring_stage != "interview":
            await self.svc._log(
                ctx,
                "Interview prep: pominięto (etap rekrutacji ≠ Rozmowa — wygeneruj ręcznie lub zmień etap)",
            )
            await self.svc._set_stage(ctx, "interview_prep", "done")
            return
        if ctx.llm_health and ctx.llm_health.get("inference_ok") is False:
            await self.svc._log(ctx, "Interview prep: pominięto (inference offline)")
            await self.svc._set_stage(ctx, "interview_prep", "done")
            return
        await self.svc._emit(cb, "interview_prep", "Interview prep…")
        await self.svc._set_stage(ctx, "interview_prep", "running")
        ctx.interview_prep_file = await self.svc.apply._generate_interview_prep(
            ctx.parsed,
            ctx.bundle,
            ctx.company_slug,
            skip_llm=ctx.llm_json_broken,
            llm_health=ctx.llm_health,
        )
        if ctx.interview_prep_file:
            await self.svc.db.update_application(
                ctx.application_id,
                interview_prep_file=ctx.interview_prep_file,
            )
            await self.svc._log(ctx, f"Interview prep: {ctx.interview_prep_file}")
        else:
            await self.svc._log(ctx, "Interview prep: pominięto (LLM offline)")
        await self.svc._set_stage(ctx, "interview_prep", "done")

    async def stage_tracker(self, ctx: PipelineContext, cb: ProgressCallback = None) -> None:
        await self.svc._emit(cb, "tracker", "Zapis do trackera…")
        await self.svc._set_stage(ctx, "tracker", "running")
        await self.svc.db.update_application(
            ctx.application_id,
            hiring_stage="ready_to_send",
        )
        if ctx.request.url:
            JobsService(self.svc.settings).update_job(
                ctx.request.url, SeenJobUpdate(status="evaluated")
            )
        await self.svc._log(ctx, "Tracker: hiring_stage=ready_to_send")
        await self.svc._set_stage(ctx, "tracker", "done")

    async def _finalize(self, ctx: PipelineContext) -> None:
        result = {
            "parsed": ctx.parsed.model_dump() if ctx.parsed else {},
            "evaluation": ctx.evaluation.model_dump() if ctx.evaluation else {},
            "reviewer": ctx.reviewer.model_dump() if ctx.reviewer else {},
            "files": ctx.files,
            "pdf_files": ctx.pdf_files,
            "verification": ctx.verification,
            "interview_prep_file": ctx.interview_prep_file,
            "tailoring_decisions": ctx.tailoring_decisions,
            "pdf_verification": ctx.pdf_verification,
            "warnings": ctx.warnings,
            "stage_timings": ctx.stage_timings,
        }
        await self.svc.db.update_apply_run(
            ctx.run_id,
            stage="completed",
            status="completed",
            result_json=json.dumps(result, ensure_ascii=False),
        )
        await self.svc._set_stage(
            ctx,
            "done",
            "done",
            extra={"pipeline_status": "done"},
        )
        self.svc._save_manifest(ctx, "done", "done")