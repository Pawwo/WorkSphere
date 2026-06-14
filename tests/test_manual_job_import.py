"""Tests for manual job import into inbox."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.models.apply import JobParsed
from app.models.jobs import ManualImportResult, SeenJobEntry
from app.services.inbox.manual_import import import_manual_job
from app.services.salary_service import SalaryAssessment
from app.storage.job_repository import JobRepository


def _settings(tmp_path: Path) -> Settings:
    scraper = tmp_path / "job_scraper"
    scraper.mkdir(parents=True)
    (scraper / "seen_jobs.json").write_text('{"seen":{}}', encoding="utf-8")
    profile = tmp_path / "profile"
    profile.mkdir()
    (profile / "01-candidate-profile.md").write_text("# Profile\nPython developer", encoding="utf-8")
    return Settings().model_copy(update={"data_dir": tmp_path.resolve(), "repo_root": tmp_path.resolve()})


@pytest.fixture
def job_parsed():
    return JobParsed(
        company="Acme Corp",
        role="Python Developer",
        location="Warszawa",
        raw_text="Python Developer at Acme Corp. Remote friendly. Django, FastAPI.",
        source="text",
    )


@pytest.fixture
def assessment():
    return SalaryAssessment(
        salary_raw="15000 PLN",
        source="description",
        monthly_b2b_min=14000,
        monthly_b2b_max=16000,
        monthly_b2b_median=15000,
        meets_threshold=True,
        reason="parsed from description",
    )


@pytest.mark.asyncio
async def test_import_manual_job_creates_entry(tmp_path, job_parsed, assessment):
    settings = _settings(tmp_path)
    url = "https://careers.acme.example/jobs/python-dev"

    with patch(
        "app.services.inbox.manual_import.fit_jobs_parallel",
        AsyncMock(return_value=[("high", assessment)]),
    ):
        with patch(
            "app.services.inbox.manual_import.enrich_highlights_for_new_jobs",
            AsyncMock(),
        ) as enrich:
            result = await import_manual_job(url=url, parsed=job_parsed, settings=settings)

    assert result.created is True
    assert result.fit == "high"
    assert result.url == url
    enrich.assert_awaited_once()

    repo = JobRepository(settings.seen_jobs_path)
    entry = repo.all()[url]
    assert entry.title == "Python Developer"
    assert entry.company == "Acme Corp"
    assert entry.import_source == "manual"
    assert entry.status == "new"
    assert entry.salary_b2b_monthly == 15000
    assert "Django" in (entry.description or "")
    assert entry.needs_deep_eval is True


@pytest.mark.asyncio
async def test_import_manual_job_backfills_missing_description(tmp_path, job_parsed, assessment):
    settings = _settings(tmp_path)
    key = "acme corp|python developer"
    seen_path = settings.seen_jobs_path
    seen_path.write_text(
        json.dumps(
            {
                "seen": {
                    key: SeenJobEntry(
                        title="Python Developer",
                        company="Acme Corp",
                        url="",
                        first_seen="2026-06-11",
                        fit="medium",
                        import_source="manual",
                    ).model_dump()
                }
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "app.services.inbox.manual_import.fit_jobs_parallel",
        AsyncMock(return_value=[("high", assessment)]),
    ):
        result = await import_manual_job(url=None, parsed=job_parsed, settings=settings)

    assert result.created is False
    entry = JobRepository(seen_path).all()[key]
    assert "Django" in (entry.description or "")


@pytest.mark.asyncio
async def test_import_manual_job_skips_duplicate_url(tmp_path, job_parsed, assessment):
    settings = _settings(tmp_path)
    url = "https://careers.acme.example/jobs/python-dev"
    seen_path = settings.seen_jobs_path
    seen_path.write_text(
        json.dumps(
            {
                "seen": {
                    url: SeenJobEntry(
                        title="Python Developer",
                        company="Acme Corp",
                        url=url,
                        first_seen="2026-06-01",
                        fit="medium",
                    ).model_dump()
                }
            }
        ),
        encoding="utf-8",
    )

    with patch(
        "app.services.inbox.manual_import.fit_jobs_parallel",
        AsyncMock(return_value=[("high", assessment)]),
    ):
        result = await import_manual_job(url=url, parsed=job_parsed, settings=settings)

    assert result.created is False
    assert result.fit == "medium"
    repo = JobRepository(seen_path)
    assert len(repo.all()) == 1


@pytest.mark.asyncio
async def test_import_manual_job_text_without_url(tmp_path, job_parsed, assessment):
    settings = _settings(tmp_path)

    with patch(
        "app.services.inbox.manual_import.fit_jobs_parallel",
        AsyncMock(return_value=[("medium", assessment)]),
    ):
        with patch(
            "app.services.inbox.manual_import.enrich_highlights_for_new_jobs",
            AsyncMock(),
        ):
            result = await import_manual_job(url=None, parsed=job_parsed, settings=settings)

    assert result.created is True
    assert result.url == ""
    assert result.key == "acme corp|python developer"

    repo = JobRepository(settings.seen_jobs_path)
    assert "acme corp|python developer" in repo.all()


@pytest.mark.asyncio
async def test_stage_parse_calls_import_manual_job(tmp_path, job_parsed):
    from app.models.apply import ApplyRequest, FitEvaluation
    from app.services.pipeline_service import PipelineService

    settings = _settings(tmp_path)
    pipeline = PipelineService(settings)
    evaluation = FitEvaluation(overall_fit="strong", recommendation="Good match")

    with patch("app.services.pipeline.stages.fetch_job_posting", AsyncMock(return_value=job_parsed)):
        with patch(
            "app.services.pipeline.stages.import_manual_job",
            AsyncMock(
                return_value=ManualImportResult(
                    created=True,
                    key="https://example.com/job",
                    url="https://example.com/job",
                    fit="high",
                    title=job_parsed.role,
                    company=job_parsed.company,
                )
            ),
        ) as import_mock:
            with patch.object(pipeline.apply, "evaluate", AsyncMock(return_value=evaluation)):
                await pipeline.run_sync(
                    ApplyRequest(url="https://example.com/job", proceed=False)
                )

    import_mock.assert_awaited_once()
