"""InboxService — unified inbox API."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.models.jobs import ManualSkipReasonItem, SkipReasonDetails, SeenJobUpdate
from app.services.inbox_service import InboxService
from app.services.inbox.skip_reason import resolve_auto_skip_category
from app.storage.job_repository import JobRepository


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
                        "triage_reason": "operations",
                        "tier": "priority",
                        "status": "new",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return Settings().model_copy(update={"data_dir": tmp_path.resolve()})


def test_inbox_list_jobs(tmp_path):
    svc = InboxService(_settings(tmp_path))
    data = svc.list_jobs(status="new")
    assert data["total"] == 1
    assert data["jobs"][0]["title"] == "Head of Operations"


def test_inbox_manual_job_without_url_has_empty_public_url(tmp_path):
    settings = _settings(tmp_path)
    seen_path = settings.seen_jobs_path
    seen = json.loads(seen_path.read_text())
    seen["seen"]["acme corp|head of operations"] = {
        "title": "Head of Operations",
        "company": "Acme Corp",
        "url": "",
        "first_seen": "2026-06-11",
        "status": "new",
        "fit": "medium",
        "import_source": "manual",
    }
    seen_path.write_text(json.dumps(seen), encoding="utf-8")
    (settings.job_scraper_dir / "triage_result.json").write_text(
        json.dumps(
            {
                "skipped_count": 0,
                "priority_count": 1,
                "review_count": 0,
                "ranked": [
                    {
                        "url": "acme corp|head of operations",
                        "title": "Head of Operations",
                        "company": "Acme Corp",
                        "quick_fit": "medium",
                        "triage_score": 65,
                        "triage_reason": "operations",
                        "tier": "priority",
                        "status": "new",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    svc = InboxService(settings)
    job = svc.load_inbox(tier="priority", status="new")["jobs"][0]
    assert job["url"] == ""
    assert job["key"] == "acme corp|head of operations"


def test_inbox_skip_syncs_triage(tmp_path):
    settings = _settings(tmp_path)
    svc = InboxService(settings)
    url = "https://example.com/job-1"
    assert svc.update_job(url, SeenJobUpdate(status="skipped")) is True
    triage = json.loads((settings.job_scraper_dir / "triage_result.json").read_text())
    assert triage["ranked"][0]["tier"] == "skip"
    inbox = svc.load_inbox(tier="skip", status="skipped")
    assert inbox["total"] == 1


def test_skipped_manual_job_outside_triage_not_counted_untriaged(tmp_path):
    settings = _settings(tmp_path)
    seen_path = settings.seen_jobs_path
    seen = json.loads(seen_path.read_text())
    seen["seen"]["acme corp|head of operations"] = {
        "title": "Head of Operations",
        "company": "Acme Corp",
        "url": "",
        "first_seen": "2026-06-11",
        "status": "skipped",
        "fit": "medium",
        "import_source": "manual",
    }
    seen_path.write_text(json.dumps(seen), encoding="utf-8")

    svc = InboxService(settings)
    counts = svc.get_counts()
    assert counts["untriaged"] == 0
    assert counts["triage_stale"] is False

    inbox = svc.load_inbox(tier="priority", status="new")
    assert inbox["triage_stale"] is False


def test_run_triage_clears_untriaged_new_jobs(tmp_path):
    settings = _settings(tmp_path)
    seen_path = settings.seen_jobs_path
    seen = json.loads(seen_path.read_text())
    seen["seen"]["https://example.com/job-2"] = {
        "title": "New Scrape Role",
        "company": "Beta",
        "url": "https://example.com/job-2",
        "first_seen": "2026-06-10",
        "status": "new",
        "fit": "medium",
    }
    seen_path.write_text(json.dumps(seen), encoding="utf-8")

    svc = InboxService(settings)
    assert svc.get_counts()["untriaged"] == 1
    svc.run_triage()
    counts = svc.get_counts()
    assert counts["untriaged"] == 0
    assert counts["triage_stale"] is False


def test_inbox_shows_untriaged_jobs_in_review_tab(tmp_path):
    settings = _settings(tmp_path)
    seen_path = settings.seen_jobs_path
    seen = json.loads(seen_path.read_text())
    seen["seen"]["https://example.com/job-2"] = {
        "title": "New Scrape Role",
        "company": "Beta",
        "url": "https://example.com/job-2",
        "first_seen": "2026-06-10",
        "status": "new",
        "fit": "medium",
    }
    seen_path.write_text(json.dumps(seen), encoding="utf-8")

    svc = InboxService(settings)
    counts = svc.get_counts()
    assert counts["untriaged"] == 1
    assert counts["triage_stale"] is True
    assert counts["inbox_badge"] == 2

    priority = svc.load_inbox(tier="priority", status="new")
    assert priority["total"] == 1
    assert priority["triage_stale"] is True

    review = svc.load_inbox(tier="review", status="new")
    assert review["total"] == 1
    assert review["jobs"][0]["title"] == "New Scrape Role"
    assert review["jobs"][0]["triage_reason"] == "Poza triażem"


def test_manual_skip_persists_skip_reason(tmp_path):
    settings = _settings(tmp_path)
    svc = InboxService(settings)
    url = "https://example.com/job-1"
    reason = SkipReasonDetails(
        reasons=[ManualSkipReasonItem(category="english_level")],
    )
    assert svc.update_job(url, SeenJobUpdate(status="skipped", skip_reason=reason)) is True

    seen = json.loads(settings.seen_jobs_path.read_text())
    entry = seen["seen"][url]
    assert entry["status"] == "skipped"
    assert entry["skip_reason"]["reasons"][0]["category"] == "english_level"
    assert entry["skip_reason"]["source"] == "manual"
    assert entry["skip_reason"]["skipped_at"]

    inbox = svc.load_inbox(tier="skip", status="skipped")
    assert inbox["jobs"][0]["skip_reason"]["reasons"][0]["category"] == "english_level"


def test_manual_skip_multiple_reasons(tmp_path):
    settings = _settings(tmp_path)
    svc = InboxService(settings)
    url = "https://example.com/job-1"
    reason = SkipReasonDetails(
        reasons=[
            ManualSkipReasonItem(category="english_level"),
            ManualSkipReasonItem(category="salary_low", salary_note="12 000 PLN B2B"),
        ],
    )
    assert svc.update_job(url, SeenJobUpdate(status="skipped", skip_reason=reason)) is True
    entry = json.loads(settings.seen_jobs_path.read_text())["seen"][url]
    cats = [r["category"] for r in entry["skip_reason"]["reasons"]]
    assert cats == ["english_level", "salary_low"]


def test_manual_skip_legacy_single_category_format():
    reason = SkipReasonDetails(category="english_level")
    assert len(reason.reasons) == 1
    assert reason.reasons[0].category == "english_level"


def test_manual_skip_validation_missing_skill():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SkipReasonDetails(category="missing_skill")


def test_manual_skip_domain_knowledge_persists(tmp_path):
    settings = _settings(tmp_path)
    svc = InboxService(settings)
    url = "https://example.com/job-1"
    reason = SkipReasonDetails(
        reasons=[ManualSkipReasonItem(category="domain_knowledge", domain_note="farmacja")],
    )
    assert svc.update_job(url, SeenJobUpdate(status="skipped", skip_reason=reason)) is True
    entry = json.loads(settings.seen_jobs_path.read_text())["seen"][url]
    assert entry["skip_reason"]["reasons"][0]["domain_note"] == "farmacja"


def test_manual_skip_validation_domain_knowledge():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SkipReasonDetails(
            reasons=[ManualSkipReasonItem(category="domain_knowledge")],
        )


def test_resolve_auto_skip_category():
    assert resolve_auto_skip_category("low", 10) == "auto_low_fit"
    assert resolve_auto_skip_category("high", -60) == "auto_low_score"
    assert resolve_auto_skip_category("low", -60) == "auto_low_fit_and_score"


def test_skip_linkedin_percent_slug_url(tmp_path):
    settings = _settings(tmp_path)
    stored = (
        "https://pl.linkedin.com/jobs/view/applied-ai-co-founder-coo-100-%25-remote-m-f-d-at-ewor-4424568863"
    )
    seen = json.loads(settings.seen_jobs_path.read_text())
    seen["seen"][stored] = {
        "title": "Applied AI Co-Founder / COO (100 % remote) (m/f/d)",
        "company": "EWOR",
        "url": stored,
        "first_seen": "2026-06-09",
        "status": "new",
        "fit": "medium",
    }
    settings.seen_jobs_path.write_text(json.dumps(seen), encoding="utf-8")
    triage = json.loads((settings.job_scraper_dir / "triage_result.json").read_text())
    triage["ranked"].append(
        {
            "url": stored,
            "title": "Applied AI Co-Founder / COO (100 % remote) (m/f/d)",
            "company": "EWOR",
            "quick_fit": "medium",
            "triage_score": 40,
            "triage_reason": "coo",
            "tier": "priority",
            "status": "new",
        }
    )
    (settings.job_scraper_dir / "triage_result.json").write_text(
        json.dumps(triage), encoding="utf-8"
    )

    repo = JobRepository(settings.seen_jobs_path)
    decoded = stored.replace("%25", "%")
    assert repo.get_by_url(decoded) is not None

    svc = InboxService(settings)
    assert svc.update_job(decoded, SeenJobUpdate(status="skipped")) is True


def test_run_triage_auto_skip_persists_skip_reason(tmp_path):
    settings = _settings(tmp_path)
    seen_path = settings.seen_jobs_path
    seen = json.loads(seen_path.read_text())
    seen["seen"]["https://example.com/job-low"] = {
        "title": "Junior Analyst",
        "company": "Acme",
        "url": "https://example.com/job-low",
        "first_seen": "2026-06-09",
        "status": "new",
        "fit": "low",
    }
    seen_path.write_text(json.dumps(seen), encoding="utf-8")

    svc = InboxService(settings)
    result = svc.run_triage()
    assert result["skipped"] >= 1

    stored = json.loads(seen_path.read_text())["seen"]["https://example.com/job-low"]
    assert stored["status"] == "skipped"
    assert stored["skip_reason"]["source"] == "auto_triage"
    assert stored["skip_reason"]["category"] == "auto_low_fit"
    assert stored["skip_reason"]["triage_score"] is not None


def test_run_triage_incremental_updates_only_given_keys(tmp_path):
    settings = _settings(tmp_path)
    seen_path = settings.seen_jobs_path
    seen = json.loads(seen_path.read_text())
    seen["seen"]["https://example.com/job-2"] = {
        "title": "Beta Role",
        "company": "Beta",
        "url": "https://example.com/job-2",
        "first_seen": "2026-06-10",
        "status": "new",
        "fit": "high",
    }
    seen_path.write_text(json.dumps(seen), encoding="utf-8")

    svc = InboxService(settings)
    svc.run_triage()
    before = json.loads((settings.job_scraper_dir / "triage_result.json").read_text())
    job1_before = next(r for r in before["ranked"] if r["url"] == "https://example.com/job-1")

    seen["seen"]["https://example.com/job-2"]["fit"] = "low"
    seen["seen"]["https://example.com/job-2"]["salary_meets_threshold"] = False
    seen["seen"]["https://example.com/job-2"]["salary_b2b_monthly"] = 12000
    seen["seen"]["https://example.com/job-2"]["salary_source"] = "direct"
    seen_path.write_text(json.dumps(seen), encoding="utf-8")

    svc.run_triage(keys={"https://example.com/job-2"})
    after = json.loads((settings.job_scraper_dir / "triage_result.json").read_text())
    job1_after = next(r for r in after["ranked"] if r["url"] == "https://example.com/job-1")
    job2_after = next(r for r in after["ranked"] if r["url"] == "https://example.com/job-2")

    assert job1_after["tier"] == job1_before["tier"]
    assert job1_after["triage_score"] == job1_before["triage_score"]
    assert job2_after["tier"] == "skip"
    assert job2_after["quick_fit"] == "low"
    assert len(after["ranked"]) == 2


def test_run_triage_incremental_leaves_evaluated_outside_keys(tmp_path):
    settings = _settings(tmp_path)
    seen_path = settings.seen_jobs_path
    seen = json.loads(seen_path.read_text())
    seen["seen"]["https://example.com/evaluated"] = {
        "title": "COO",
        "company": "TrackerCo",
        "url": "https://example.com/evaluated",
        "first_seen": "2026-06-11",
        "status": "evaluated",
        "fit": "low",
    }
    seen["seen"]["https://example.com/job-new"] = {
        "title": "Fresh Role",
        "company": "Beta",
        "url": "https://example.com/job-new",
        "first_seen": "2026-06-14",
        "status": "new",
        "fit": "low",
    }
    seen_path.write_text(json.dumps(seen), encoding="utf-8")

    svc = InboxService(settings)
    svc.run_triage()
    svc.run_triage(keys={"https://example.com/job-new"})

    stored = json.loads(seen_path.read_text())["seen"]
    assert stored["https://example.com/evaluated"]["status"] == "evaluated"
    assert stored["https://example.com/job-new"]["status"] == "skipped"
