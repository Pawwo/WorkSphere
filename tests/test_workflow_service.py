"""Workflow inbox — skip syncs triage + seen_jobs."""

import json
from pathlib import Path

from app.config import Settings
from app.models.jobs import SeenJobUpdate
from app.services.jobs_service import JobsService
from app.services.workflow_service import WorkflowService


def _settings(tmp_path: Path) -> Settings:
    scraper_dir = tmp_path / "job_scraper"
    scraper_dir.mkdir(parents=True)
    seen_path = scraper_dir / "seen_jobs.json"
    seen_path.write_text(
        json.dumps(
            {
                "seen": {
                    "https://example.com/job-1": {
                        "title": "Head of Operations",
                        "company": "Acme",
                        "url": "https://example.com/job-1",
                        "first_seen": "2026-06-09",
                        "status": "new",
                        "fit": "high",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (scraper_dir / "triage_result.json").write_text(
        json.dumps(
            {
                "skipped_count": 0,
                "priority_count": 1,
                "review_count": 0,
                "ranked": [
                    {
                        "url": "https://example.com/job-1",
                        "title": "Head of Operations",
                        "company": "Acme",
                        "quick_fit": "high",
                        "triage_score": 50,
                        "triage_reason": "strong:head of operations",
                        "tier": "priority",
                        "status": "new",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return Settings().model_copy(update={"data_dir": tmp_path.resolve()})


def test_skip_moves_job_from_priority_to_skip_tab(tmp_path):
    settings = _settings(tmp_path)
    url = "https://example.com/job-1"

    ok = JobsService(settings).update_job(url, SeenJobUpdate(status="skipped"))
    assert ok is True

    triage = json.loads((settings.job_scraper_dir / "triage_result.json").read_text())
    item = triage["ranked"][0]
    assert item["tier"] == "skip"
    assert item["status"] == "skipped"
    assert triage["priority_count"] == 0
    assert triage["skipped_count"] == 1

    inbox = WorkflowService(settings).load_inbox(tier="priority", status="new")
    assert inbox["total"] == 0

    skipped = WorkflowService(settings).load_inbox(tier="skip", status="skipped")
    assert skipped["total"] == 1
    assert skipped["jobs"][0]["url"] == url
