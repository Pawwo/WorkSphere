"""Tests for Pi gap import."""

from __future__ import annotations

import json
from pathlib import Path

from app.models.jobs import SeenJobEntry
from app.services.pi_gap_sync import (
    PiJob,
    import_pi_gaps,
    is_importable,
    load_worksphere_url_keys,
    map_pi_fit,
    norm_url,
    pi_jobs_missing_from_worksphere,
    portal_from_url,
)
from app.storage.job_repository import JobRepository


def test_norm_url_strips_query():
    assert norm_url("https://Example.COM/job?x=1") == "https://example.com/job"


def test_portal_from_url():
    assert portal_from_url("https://justjoin.it/job-offer/foo") == "justjoin"
    assert portal_from_url("https://www.pracuj.pl/praca/x,oferta,1") == "pracuj"


def test_is_importable_filters():
    good = PiJob("u", "t", "c", 90, "✅", "jf", "linkedin-pl")
    yellow = PiJob("u2", "t", "c", 75, "🟨", "jf", "pracuj")
    red = PiJob("u3", "t", "c", 40, "🟥", "jf", "pracuj")
    assert is_importable(good, min_score=72, import_all=False)
    assert is_importable(yellow, min_score=72, import_all=False)
    assert not is_importable(red, min_score=72, import_all=False)


def test_map_pi_fit():
    assert map_pi_fit(PiJob("u", "t", "c", 90, "✅", "", "x")) == "high"
    assert map_pi_fit(PiJob("u", "t", "c", 75, "🟨", "", "x")) == "medium"


def test_import_pi_gaps_skips_existing(tmp_path: Path):
    seen_path = tmp_path / "seen_jobs.json"
    seen_path.write_text(
        json.dumps(
            {
                "seen": {
                    "https://existing.example/job": SeenJobEntry(
                        title="Old",
                        company="Co",
                        url="https://existing.example/job",
                        first_seen="2026-06-09",
                    ).model_dump()
                }
            }
        ),
        encoding="utf-8",
    )
    jobs = [
        PiJob("https://existing.example/job", "Old", "Co", 90, "✅", "jf", "other"),
        PiJob("https://new.example/job", "New Role", "Acme", 84, "✅", "rag", "justjoin"),
    ]
    n = import_pi_gaps(jobs, seen_path)
    assert n == 1
    repo = JobRepository(seen_path)
    all_jobs = repo.all()
    assert len(all_jobs) == 2
    new_entry = next(v for v in all_jobs.values() if v.title == "New Role")
    assert new_entry.import_source == "pi_import"
    assert new_entry.pi_score == 84
    assert new_entry.fit == "high"


def test_pi_jobs_missing_from_worksphere():
    worksphere = {norm_url("https://a.com/1")}
    pi = {
        norm_url("https://a.com/1"): PiJob("https://a.com/1", "A", "X", 1, "✅", "", "x"),
        norm_url("https://b.com/2"): PiJob("https://b.com/2", "B", "Y", 2, "✅", "", "x"),
    }
    missing = pi_jobs_missing_from_worksphere(pi, worksphere)
    assert len(missing) == 1
    assert missing[0].title == "B"


def test_load_worksphere_url_keys(tmp_path: Path):
    path = tmp_path / "seen.json"
    path.write_text(
        json.dumps({"seen": {"https://X.com/y": {"title": "t", "company": "c", "url": "https://X.com/y", "first_seen": "2026-06-10"}}}),
        encoding="utf-8",
    )
    keys = load_worksphere_url_keys(path)
    assert "https://x.com/y" in keys
