"""Pipeline staged apply — unit tests with mocked LLM stages."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.models.apply import ApplyRequest, FitEvaluation, JobParsed, ReviewerResult
from app.services.pipeline_service import PipelineService, mark_llm_warm


def _settings(tmp_path: Path) -> Settings:
    scraper = tmp_path / "job_scraper"
    scraper.mkdir(parents=True)
    (scraper / "seen_jobs.json").write_text('{"seen":{}}', encoding="utf-8")
    profile = tmp_path / "profile"
    profile.mkdir()
    for name in (
        "01-candidate-profile.md",
        "02-behavioral-profile.md",
        "04-job-evaluation.md",
        "05-cv-templates.md",
        "06-cover-letter-templates.md",
    ):
        (profile / name).write_text(f"# {name}\nName: Test User\nemail@test.com", encoding="utf-8")
    return Settings().model_copy(update={"data_dir": tmp_path.resolve(), "repo_root": tmp_path.resolve()})


@pytest.fixture
def job_parsed():
    return JobParsed(
        company="Acme Corp",
        role="Head of Operations",
        raw_text="Head of Operations at Acme. ERP Odoo transformation.",
        source="text",
    )


@pytest.fixture
def evaluation():
    return FitEvaluation(overall_fit="strong", recommendation="Good match")


@pytest.mark.asyncio
async def test_evaluate_gate_stops_without_proceed(tmp_path, job_parsed, evaluation):
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)

    with patch("app.services.pipeline.stages.fetch_job_posting", AsyncMock(return_value=job_parsed)):
        with patch.object(pipeline.apply, "evaluate", AsyncMock(return_value=evaluation)):
            resp = await pipeline.run_sync(ApplyRequest(text="job", proceed=False))

    assert resp.stage == "evaluated"
    assert resp.evaluation.overall_fit == "strong"

    row = await pipeline.db.get_application(1)
    assert row["pipeline_stage"] == "proceed"
    assert row["pipeline_status"] == "waiting"

    manifest = json.loads(
        (settings.data_dir / "applications" / "acme_corp" / "manifest.json").read_text()
    )
    assert manifest["pipeline_stage"] == "proceed"


@pytest.mark.asyncio
async def test_interview_prep_skips_when_not_interview_stage(tmp_path, job_parsed):
    settings = _settings(tmp_path).model_copy(update={"pipeline_interview_prep_enabled": True})
    pipeline = PipelineService(settings)
    ctx = await pipeline.create_application(ApplyRequest(text="job", proceed=True))
    ctx.parsed = job_parsed
    ctx.company_slug = "acme"
    ctx.bundle = {}
    ctx.llm_health = {"ok": True, "inference_ok": True}
    await pipeline.db.update_application(ctx.application_id, hiring_stage="applied")

    with patch.object(pipeline.apply, "_generate_interview_prep", AsyncMock()) as gen:
        await pipeline.stages.stage_interview_prep(ctx)

    gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_interview_prep_runs_on_interview_stage(tmp_path, job_parsed):
    settings = _settings(tmp_path).model_copy(update={"pipeline_interview_prep_enabled": True})
    pipeline = PipelineService(settings)
    ctx = await pipeline.create_application(ApplyRequest(text="job", proceed=True))
    ctx.parsed = job_parsed
    ctx.company_slug = "acme"
    ctx.bundle = {}
    ctx.llm_health = {"ok": True, "inference_ok": True}
    await pipeline.db.update_application(ctx.application_id, hiring_stage="interview")

    with patch.object(
        pipeline.apply,
        "_generate_interview_prep",
        AsyncMock(return_value="data/applications/acme/interview_prep.md"),
    ) as gen:
        await pipeline.stages.stage_interview_prep(ctx)

    gen.assert_awaited_once()


@pytest.mark.asyncio
async def test_checklist_before_interview_prep_order(tmp_path, job_parsed, evaluation):
    """Verify stage order: checklist runs before interview_prep."""
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)
    order: list[str] = []

    async def track_checklist(ctx, cb=None):
        order.append("checklist")
        ctx.verification = {"passed": 1, "total": 1, "all_pass": True, "items": []}
        await pipeline._set_stage(ctx, "checklist", "done")

    async def track_prep(ctx, cb=None):
        order.append("interview_prep")
        ctx.interview_prep_file = None
        await pipeline._set_stage(ctx, "interview_prep", "done")

    with patch("app.services.pipeline.stages.fetch_job_posting", AsyncMock(return_value=job_parsed)):
        with patch.object(pipeline.apply, "evaluate", AsyncMock(return_value=evaluation)):
            with patch.object(pipeline.stages, "stage_draft", AsyncMock(side_effect=lambda ctx, cb=None: order.append("draft"))):
                with patch.object(pipeline.stages, "stage_review", AsyncMock(side_effect=lambda ctx, cb=None: order.append("review"))):
                    with patch.object(pipeline.stages, "stage_pdf", AsyncMock(side_effect=lambda ctx, cb=None: order.append("pdf"))):
                        with patch.object(pipeline.stages, "stage_checklist", track_checklist):
                            with patch.object(pipeline.stages, "stage_interview_prep", track_prep):
                                with patch.object(pipeline.stages, "stage_tracker", AsyncMock()):
                                    with patch.object(pipeline.stages, "_finalize", AsyncMock()):
                                        ctx = await pipeline.create_application(
                                            ApplyRequest(text="job", proceed=True)
                                        )
                                        ctx.parsed = job_parsed
                                        ctx.evaluation = evaluation
                                        ctx.company_slug = "acme_corp"
                                        ctx.role_slug = "head_of_operations"
                                        ctx.application_dir = "data/applications/acme_corp"
                                        ctx.bundle = pipeline.apply._read_profile_bundle()
                                        await pipeline._run_post_proceed(ctx, None)

    assert order.index("checklist") < order.index("interview_prep")


@pytest.mark.asyncio
async def test_proceed_rebuilds_context_without_name_error(tmp_path, job_parsed, evaluation):
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)
    ctx = await pipeline.create_application(ApplyRequest(url="https://example.com/job", proceed=False))
    ctx.parsed = job_parsed
    ctx.evaluation = evaluation
    ctx.company_slug = "acme_corp"
    ctx.role_slug = "head_of_operations"
    ctx.application_dir = "data/applications/acme_corp"
    (settings.repo_root / ctx.application_dir).mkdir(parents=True, exist_ok=True)
    (settings.repo_root / ctx.application_dir / "parsed.json").write_text(
        json.dumps(job_parsed.model_dump()), encoding="utf-8"
    )
    (settings.repo_root / ctx.application_dir / "evaluation.json").write_text(
        json.dumps(evaluation.model_dump()), encoding="utf-8"
    )
    await pipeline.db.update_application(
        ctx.application_id,
        pipeline_stage="proceed",
        pipeline_status="waiting",
        company_slug=ctx.company_slug,
        application_dir=ctx.application_dir,
    )

    with patch.object(pipeline, "_run_post_proceed", AsyncMock()) as post:
        resp = await pipeline.proceed(ctx.application_id, compile_pdf=False)

    post.assert_awaited_once()
    assert resp.stage == "completed"


@pytest.mark.asyncio
async def test_retry_evaluate_refreshes_evaluation(tmp_path, job_parsed, evaluation):
    _LLM_HC = {"ok": True, "inference_ok": True}
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)
    ctx = await pipeline.create_application(ApplyRequest(url="https://example.com/job", proceed=False))
    app_dir = settings.repo_root / "data/applications/acme_corp"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "parsed.json").write_text(json.dumps(job_parsed.model_dump()), encoding="utf-8")
    fresh = FitEvaluation(overall_fit="strong", recommendation="Apply with tailored COO narrative.")
    await pipeline.db.update_application(
        ctx.application_id,
        company_slug="acme_corp",
        application_dir="data/applications/acme_corp",
        run_id=ctx.run_id,
        recommendation="LLM niedostępny — kontynuuj ręczną weryfikację dopasowania.",
    )
    await pipeline.db.update_apply_run(
        ctx.run_id,
        stage="evaluated",
        status="completed",
        result_json=json.dumps({"parsed": job_parsed.model_dump()}),
    )

    with patch.object(pipeline, "_wake_llm", AsyncMock(return_value=_LLM_HC)):
        with patch.object(pipeline.apply, "evaluate", AsyncMock(return_value=fresh)):
            with patch.object(pipeline.stages, "_finalize", AsyncMock()):
                resp = await pipeline.retry_stage(ctx.application_id, "evaluate")

    assert resp.evaluation.recommendation == "Apply with tailored COO narrative."
    row = await pipeline.db.get_application(ctx.application_id)
    assert row["recommendation"] == "Apply with tailored COO narrative."


@pytest.mark.asyncio
async def test_wake_llm_before_proceed_and_retry(tmp_path, job_parsed, evaluation):
    _LLM_HC = {"ok": True, "inference_ok": True}
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)
    ctx = await pipeline.create_application(ApplyRequest(url="https://example.com/job", proceed=False))
    ctx.parsed = job_parsed
    ctx.evaluation = evaluation
    ctx.company_slug = "acme_corp"
    ctx.role_slug = "head_of_operations"
    ctx.application_dir = "data/applications/acme_corp"
    app_dir = settings.repo_root / ctx.application_dir
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "parsed.json").write_text(json.dumps(job_parsed.model_dump()), encoding="utf-8")
    (app_dir / "evaluation.json").write_text(json.dumps(evaluation.model_dump()), encoding="utf-8")
    await pipeline.db.update_application(
        ctx.application_id,
        pipeline_stage="proceed",
        pipeline_status="waiting",
        company_slug=ctx.company_slug,
        application_dir=ctx.application_dir,
        run_id=ctx.run_id,
    )
    await pipeline.db.update_apply_run(
        ctx.run_id,
        stage="evaluated",
        status="running",
        result_json=json.dumps(
            {"parsed": job_parsed.model_dump(), "evaluation": evaluation.model_dump()}
        ),
    )

    with patch.object(pipeline, "_wake_llm", AsyncMock(return_value=_LLM_HC)) as wake:
        with patch.object(pipeline, "_run_post_proceed", AsyncMock()):
            await pipeline.proceed(ctx.application_id, compile_pdf=False)
        wake.assert_awaited()
        assert wake.await_count >= 1

    with patch.object(pipeline, "_wake_llm", AsyncMock(return_value=_LLM_HC)) as wake_retry:
        with patch.object(pipeline, "_run_post_proceed", AsyncMock()):
            await pipeline.retry_stage(ctx.application_id, "draft", compile_pdf=False)
        wake_retry.assert_awaited()
        assert wake_retry.await_count >= 1


@pytest.mark.asyncio
async def test_create_application_reuses_existing_url(tmp_path):
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)
    url = "https://example.com/job/123"
    req = ApplyRequest(url=url, text=None, proceed=False)

    ctx1 = await pipeline.create_application(req, task_id="task-1")
    ctx2 = await pipeline.create_application(req, task_id="task-2")

    assert ctx1.application_id == ctx2.application_id
    assert ctx2.run_id != ctx1.run_id
    row = await pipeline.db.get_application(ctx1.application_id)
    assert row["task_id"] == "task-2"
    assert row["pipeline_status"] == "running"
    assert row["hiring_stage"] == "draft"


@pytest.mark.asyncio
async def test_stage_tracker_sets_ready_to_send(tmp_path, job_parsed):
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)
    ctx = await pipeline.create_application(ApplyRequest(text="job", proceed=True))
    ctx.parsed = job_parsed

    with patch("app.services.pipeline.stages.JobsService") as jobs_cls:
        jobs_cls.return_value.update_job = MagicMock()
        await pipeline.stages.stage_tracker(ctx)

    row = await pipeline.db.get_application(ctx.application_id)
    assert row["hiring_stage"] == "ready_to_send"


@pytest.mark.asyncio
async def test_tracker_dedup_by_url(tmp_path):
    import aiosqlite

    settings = _settings(tmp_path)
    db = PipelineService(settings).db
    id1 = await db.create_application(company="A", role="R", url="https://example.com/job")
    with pytest.raises(aiosqlite.IntegrityError):
        await db.create_application(company="A2", role="R2", url="https://example.com/job")
    existing = await db.get_application_by_url("https://example.com/job")
    assert existing is not None
    assert existing["id"] == id1


@pytest.mark.asyncio
async def test_wake_llm_trust_after_mark_llm_warm(tmp_path):
    """P1: recent evaluate marks LLM warm — proceed skips full wake."""
    settings = _settings(tmp_path).model_copy(
        update={"pipeline_llm_warm_fast_trust": True, "pipeline_llm_warm_cache_seconds": 600}
    )
    pipeline = PipelineService(settings)
    mark_llm_warm()

    with patch.object(pipeline, "_wake_llm", wraps=pipeline._wake_llm) as wake:
        hc = await pipeline._wake_llm(trust_recent=True)

    assert hc.get("warm_cache") == "trust"
    assert hc.get("ok") is True
    wake.assert_awaited_once()


@pytest.mark.asyncio
async def test_evaluate_prefetches_company_search(tmp_path, job_parsed, evaluation):
    """P2: SearXNG prefetch runs during evaluate."""
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)
    ctx = await pipeline.create_application(ApplyRequest(text="job", proceed=False))
    ctx.parsed = job_parsed

    with patch.object(
        pipeline.apply, "prefetch_company_search", AsyncMock(return_value=None)
    ) as prefetch:
        with patch.object(pipeline.apply, "evaluate", AsyncMock(return_value=evaluation)):
            await pipeline.stages.stage_evaluate(ctx)

    prefetch.assert_awaited_once_with("Acme Corp")
