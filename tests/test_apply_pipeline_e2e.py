"""Apply pipeline integration tests (mocked LLM/LaTeX)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.models.apply import ApplyRequest, FitEvaluation, JobParsed, ReviewerResult
from app.services.cv.language import draft_has_language_mismatch
from app.services.cv.types import CvDraftData, EducationEntry, ExperienceEntry
from app.services.cv_tailor_service import CvTailorError, CvTailorService
from app.services.pipeline_service import PipelineService
from app.services.task_service import TaskService


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
        (profile / name).write_text(
            f"# {name}\n- **Name:** Test User\n- **Email:** email@test.com\n",
            encoding="utf-8",
        )
    (tmp_path / "cv").mkdir(exist_ok=True)
    (tmp_path / "cover_letters").mkdir(exist_ok=True)
    return Settings().model_copy(update={"data_dir": tmp_path.resolve(), "repo_root": tmp_path.resolve()})


@pytest.fixture
def job_parsed():
    return JobParsed(
        company="Acme Corp",
        role="Head of Operations",
        raw_text="Head of Operations at Acme. ERP Odoo.",
        source="text",
        language="en",
    )


@pytest.fixture
def evaluation():
    return FitEvaluation(overall_fit="strong", recommendation="Good match")


@pytest.mark.asyncio
async def test_evaluate_gate_no_cv_files(tmp_path, job_parsed, evaluation):
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)

    with patch("app.services.pipeline.stages.fetch_job_posting", AsyncMock(return_value=job_parsed)):
        with patch.object(pipeline.apply, "evaluate", AsyncMock(return_value=evaluation)):
            ctx = await pipeline.create_application(ApplyRequest(text="job", proceed=False), task_id="t1")
            result = await pipeline.run_async(
                ApplyRequest(text="job", proceed=False),
                "t1",
                on_progress=None,
                ctx=ctx,
            )

    assert result["status"] == "waiting"
    row = await pipeline.db.get_application(ctx.application_id)
    assert row["pipeline_stage"] == "proceed"
    assert row["cv_file"] is None


@pytest.mark.asyncio
async def test_tailor_fallback_on_llm_error(tmp_path, job_parsed):
    settings = _settings(tmp_path)
    tailor = CvTailorService(settings)
    baseline = CvDraftData(
        profile_statement="Base",
        competencies=["Ops: ERP"],
        experience_entries=[
            ExperienceEntry(
                period="2020 - Present",
                title="COO",
                company="Test Co",
                location="PL",
                bullets=["Led ERP rollout"],
            )
        ],
        education_entries=[
            EducationEntry(period="2003", degree="BSc", institution="Uni", location="PL", detail="CS")
        ],
    )
    cover = {"opening": "Hello", "bullets": ["One"]}

    with patch.object(tailor, "_resolve_targets", AsyncMock(side_effect=CvTailorError("offline"))):
        result = await tailor.tailor_application_with_fallback(
            job_parsed,
            baseline=baseline,
            profile_md="# profile",
            behavioral_md="",
            cover_default=cover,
        )

    assert "Base" in result.cv_draft.profile_statement
    assert result.cover_data["opening"] == "Hello"
    assert any("baseline" in d.lower() for d in result.tailoring_decisions)


@pytest.mark.asyncio
async def test_tailor_fallback_translates_polish_bullets_for_en_job(tmp_path, job_parsed):
    settings = _settings(tmp_path)
    tailor = CvTailorService(settings)
    baseline = CvDraftData(
        profile_statement="Chief Operating Officer with ERP experience.",
        competencies=["Ops: ERP"],
        experience_entries=[
            ExperienceEntry(
                period="2020 - Present",
                title="COO",
                company="Test Co",
                location="PL",
                bullets=["Zarządzanie całością operacji firmy."],
            )
        ],
        education_entries=[
            EducationEntry(period="2003", degree="BSc", institution="Uni", location="PL", detail="CS")
        ],
        cv_language="en",
    )
    cover = {"opening": "Hello", "bullets": ["One"]}

    async def fake_align(draft, job, *, profile_md="", llm_degraded=False):
        draft.experience_entries = [
            ExperienceEntry(
                period=e.period,
                title=e.title,
                company=e.company,
                location=e.location,
                bullets=["Managing company-wide operations."],
            )
            for e in draft.experience_entries
        ]
        return draft, ["CV language aligned via offline bullet translation fallback."]

    with patch.object(tailor, "_resolve_targets", AsyncMock(side_effect=CvTailorError("offline"))):
        with patch.object(tailor, "_align_cv_language", AsyncMock(side_effect=fake_align)):
            result = await tailor.tailor_application_with_fallback(
                job_parsed,
                baseline=baseline,
                profile_md="# profile",
                behavioral_md="",
                cover_default=cover,
            )

    assert not draft_has_language_mismatch(result.cv_draft, "en")
    assert result.cv_draft.experience_entries[0].bullets == ["Managing company-wide operations."]
    assert any("baseline" in d.lower() for d in result.tailoring_decisions)


@pytest.mark.asyncio
async def test_persist_tex_after_review(tmp_path, job_parsed, evaluation):
    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)
    ctx = await pipeline.create_application(ApplyRequest(text="job", proceed=True), task_id="t2")
    ctx.parsed = job_parsed
    ctx.evaluation = evaluation
    ctx.company_slug = "acme_corp"
    ctx.role_slug = "head_of_operations"
    ctx.application_dir = "data/applications/acme_corp"
    ctx._cv_tex = "% CV tex"
    ctx._cover_tex = "% cover tex"
    ctx.reviewer = ReviewerResult(overall_verdict="approve")

    with patch.object(pipeline.stages, "stage_draft", AsyncMock()):
        with patch.object(pipeline.stages, "stage_review", AsyncMock()):
            await pipeline.stages.stage_persist_tex(ctx)

    row = await pipeline.db.get_application(ctx.application_id)
    assert row["cv_file"]
    assert row["cover_file"]
    assert (settings.repo_root / row["cv_file"]).exists()
    assert row["cv_file"].endswith("Resume_Test_User_Acme_Corp.html")
    assert row["cover_file"].endswith("Cover_Test_User_Acme_Corp.html")


@pytest.mark.asyncio
async def test_task_events_persisted(tmp_path):
    settings = _settings(tmp_path)
    from app.storage.db import Database

    TaskService._instance = None
    tasks = TaskService()
    pipeline_db = Database(settings.db_path)
    tasks.db = pipeline_db

    task_id = await tasks.create("apply")
    await tasks.emit(task_id, "parse", 10, "Parsing")
    await tasks.complete(task_id, {"ok": True})

    events = await pipeline_db.list_task_events(task_id)
    assert len(events) >= 2
    assert events[0]["stage"] == "parse"
    assert events[-1]["status"] == "completed"
