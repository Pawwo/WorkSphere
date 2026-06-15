"""Tests for strict English requirement detection in triage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.models.jobs import SeenJobEntry
from app.models.setup import LanguageEntry, WizardSection1, WizardState
from app.services.inbox.language_triage import (
    detect_strict_english_requirement,
    extract_language_requirements,
    job_posting_blob,
)
from app.services.inbox_service import InboxService


@pytest.mark.parametrize(
    "text,expected_token",
    [
        ("Fluent English: C1/C2 EU citizenship", "english_fluent"),
        (
            "Fluent English and experience in international environment",
            "english_fluent",
        ),
        ("excellent command of English required", "english_excellent"),
        ("Requirements: English (C1+)", "english_c1_plus"),
        ("Znajomość języka angielskiego (C1)", "english_c1"),
        ("Qualifications: Very good English skills (minimum C1)", "english_c1"),
        (
            "Fluent communication skills in English and Polish",
            "english_fluent",
        ),
    ],
)
def test_detect_strict_english_positive(text: str, expected_token: str):
    skip, token = detect_strict_english_requirement(text)
    assert skip is True
    assert token == expected_token


@pytest.mark.parametrize(
    "text",
    [
        "English on a B2/C1 level",
        "min. B2/C1 in spoken and written English",
        "advanced English skills",
        "Candidate is fluent in Polish and has advanced English skills",
        "",
        "Python developer with Django experience",
    ],
)
def test_detect_strict_english_negative(text: str):
    skip, token = detect_strict_english_requirement(text)
    assert skip is False
    assert token is None


def test_ensure_posting_blob_fetches_when_only_long_title(tmp_path):
    from app.services.inbox.language_triage import ensure_posting_blob

    job = SeenJobEntry(
        title="Starszy Menedżer/Menedżerka Produktu Cyfrowego (Senior Product Manager - Commerce Platform)",
        company="LUX MED Sp. z o.o.",
        url="https://example.com/job",
        first_seen="2026-06-11",
    )
    fetched_text = "Wymagane języki: angielski. Angielski C1 required for daily work."
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.services.inbox.language_triage.fetch_posting_text_sync",
            lambda url, timeout=20.0: fetched_text,
        )
        blob, stored = ensure_posting_blob(job)
    assert stored == fetched_text
    assert "Angielski C1" in blob
    assert detect_strict_english_requirement(blob) == (True, "english_c1")


def test_job_posting_blob_uses_salary_raw_not_highlights():
    job = SeenJobEntry(
        title="Scrum Master",
        company="Acme",
        url="https://example.com/job",
        first_seen="2026-06-11",
        salary_raw="Fluent English required for daily standups.",
        highlights=["Candidate is fluent in Polish and advanced English"],
    )
    blob = job_posting_blob(job)
    assert "Fluent English" in blob
    assert "Candidate is fluent" not in blob
    assert detect_strict_english_requirement(blob) == (True, "english_fluent")


def _write_profile(
    tmp_path: Path,
    *,
    english_level: str = "B2",
) -> None:
    setup = tmp_path / "setup"
    setup.mkdir(exist_ok=True)
    state = WizardState(
        section1=WizardSection1(
            full_name="Jan Kowalski",
            location="Kraków",
            email="jan@example.com",
            language_skills=[
                LanguageEntry(language="polish", level="native"),
                LanguageEntry(language="english", level=english_level),  # type: ignore[arg-type]
                LanguageEntry(language="german", level="A2"),
            ],
        )
    )
    (setup / "wizard_state.json").write_text(state.model_dump_json(), encoding="utf-8")


def _settings(tmp_path: Path, *, english_level: str = "B2") -> Settings:
    scraper = tmp_path / "job_scraper"
    scraper.mkdir()
    _write_profile(tmp_path, english_level=english_level)
    seen = {
        "https://example.com/fluent": {
            "title": "Operations Lead",
            "company": "Global Co",
            "url": "https://example.com/fluent",
            "first_seen": "2026-06-11",
            "status": "new",
            "fit": "high",
            "salary_raw": "We need Fluent English: C1/C2 for this leadership role.",
        },
        "https://example.com/b2c1": {
            "title": "Team Leader",
            "company": "Local Co",
            "url": "https://example.com/b2c1",
            "first_seen": "2026-06-11",
            "status": "new",
            "fit": "medium",
            "salary_raw": "English on a B2/C1 level required.",
        },
    }
    (scraper / "seen_jobs.json").write_text(json.dumps({"seen": seen}), encoding="utf-8")
    return Settings().model_copy(update={"data_dir": tmp_path.resolve()})


def test_extract_language_requirements_german():
    reqs = extract_language_requirements("Fluent German required for daily work.")
    assert any(r.language == "german" and r.level == "C1" for r in reqs)


def test_run_triage_no_language_skip_without_profile(tmp_path: Path):
    scraper = tmp_path / "job_scraper"
    scraper.mkdir()
    seen = {
        "https://example.com/fluent": {
            "title": "Operations Lead",
            "company": "Global Co",
            "url": "https://example.com/fluent",
            "first_seen": "2026-06-11",
            "status": "new",
            "fit": "high",
            "salary_raw": "We need Fluent English: C1/C2 for this leadership role.",
        },
    }
    (scraper / "seen_jobs.json").write_text(json.dumps({"seen": seen}), encoding="utf-8")
    settings = Settings().model_copy(update={"data_dir": tmp_path.resolve()})
    result = InboxService(settings).run_triage()
    assert result["skipped"] == 0
    entry = json.loads((tmp_path / "job_scraper" / "seen_jobs.json").read_text())["seen"][
        "https://example.com/fluent"
    ]
    assert entry["status"] == "new"


def test_run_triage_does_not_skip_tracker_evaluated_job(tmp_path: Path):
    settings = _settings(tmp_path)
    seen_path = settings.seen_jobs_path
    seen = json.loads(seen_path.read_text())
    seen["seen"]["https://example.com/evaluated"] = {
        "title": "COO",
        "company": "UltaHost",
        "url": "https://example.com/evaluated",
        "first_seen": "2026-06-11",
        "status": "evaluated",
        "fit": "medium",
        "salary_raw": "excellent command of English required.",
    }
    seen_path.write_text(json.dumps(seen), encoding="utf-8")

    svc = InboxService(settings)
    triage = svc.run_triage()

    entry = json.loads(seen_path.read_text())["seen"]["https://example.com/evaluated"]
    assert entry["status"] == "evaluated"
    assert entry.get("skip_reason") is None
    row = next(r for r in json.loads((tmp_path / "job_scraper" / "triage_result.json").read_text())["ranked"] if r["url"] == "https://example.com/evaluated")
    assert row["tier"] == "skip"
    assert row["status"] == "evaluated"


def test_run_triage_auto_skips_fluent_english(tmp_path: Path):
    svc = InboxService(_settings(tmp_path))
    result = svc.run_triage()

    assert result["skipped"] >= 1
    triage = json.loads((tmp_path / "job_scraper" / "triage_result.json").read_text())
    tiers = {r["url"]: r for r in triage["ranked"]}

    fluent = tiers["https://example.com/fluent"]
    assert fluent["tier"] == "skip"
    assert fluent["status"] == "skipped"
    assert fluent["skip_reason"]["category"] == "auto_language_level"
    assert "english_fluent" in (fluent["triage_reason"] or "")

    b2c1 = tiers["https://example.com/b2c1"]
    assert b2c1["tier"] != "skip"
    assert b2c1["status"] == "new"

    seen = json.loads((tmp_path / "job_scraper" / "seen_jobs.json").read_text())
    assert seen["seen"]["https://example.com/fluent"]["status"] == "skipped"
    assert seen["seen"]["https://example.com/b2c1"]["status"] == "new"


def test_run_triage_keeps_c1_job_when_profile_has_c1(tmp_path: Path):
    settings = _settings(tmp_path, english_level="C1")
    result = InboxService(settings).run_triage()
    tiers = {
        r["url"]: r
        for r in json.loads((tmp_path / "job_scraper" / "triage_result.json").read_text())[
            "ranked"
        ]
    }
    fluent = tiers["https://example.com/fluent"]
    assert fluent["status"] == "new"
    assert fluent["tier"] != "skip"
    assert result["skipped"] == 0


def test_run_triage_retriage_preserves_language_skip_tier(tmp_path: Path):
    from app.services.inbox.skip_reason import build_auto_language_skip_reason

    settings = _settings(tmp_path)
    seen_path = settings.seen_jobs_path
    seen = json.loads(seen_path.read_text())
    url = "https://example.com/fluent"
    seen["seen"][url]["status"] = "skipped"
    seen["seen"][url]["skip_reason"] = build_auto_language_skip_reason(
        language="english",
        level="C1",
        triage_score=30,
        triage_reason="strong:\\bcoo\\b, english_c1",
        quick_fit="high",
        matched_token="english_c1",
    ).model_dump()
    seen_path.write_text(json.dumps(seen), encoding="utf-8")

    svc = InboxService(settings)
    svc.run_triage()

    triage = json.loads((tmp_path / "job_scraper" / "triage_result.json").read_text())
    row = next(r for r in triage["ranked"] if r["url"] == url)
    assert row["tier"] == "skip"
    assert row["status"] == "skipped"
    assert row["skip_reason"]["category"] == "auto_language_level"

    queue = json.loads((tmp_path / "job_scraper" / "evaluate_queue.json").read_text())
    assert url not in queue.get("urls", [])
