import json
from pathlib import Path

from app.config import Settings
from app.services.inbox_service import InboxService


def _settings(tmp_path: Path) -> Settings:
    scraper = tmp_path / "job_scraper"
    scraper.mkdir()
    seen = {
        "https://example.com/coo": {
            "title": "Chief Operating Officer",
            "company": "Venture Co",
            "url": "https://example.com/coo",
            "first_seen": "2026-06-11",
            "status": "new",
            "fit": "high",
        },
        "https://example.com/pi": {
            "title": "Product Owner",
            "company": "Corp",
            "url": "https://example.com/pi",
            "first_seen": "2026-06-11",
            "status": "new",
            "fit": "medium",
            "pi_score": 78,
            "pi_verdict": "🟨",
        },
    }
    (scraper / "seen_jobs.json").write_text(json.dumps({"seen": seen}), encoding="utf-8")
    return Settings().model_copy(update={"data_dir": tmp_path.resolve()})


def test_run_triage_puts_high_and_pi_boost_in_priority(tmp_path: Path):
    svc = InboxService(_settings(tmp_path))
    result = svc.run_triage()
    assert result["priority"] >= 2
    triage = json.loads((tmp_path / "job_scraper" / "triage_result.json").read_text())
    tiers = {r["url"]: r["tier"] for r in triage["ranked"]}
    assert tiers["https://example.com/coo"] == "priority"
    assert tiers["https://example.com/pi"] == "priority"
