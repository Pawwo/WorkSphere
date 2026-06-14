import json
from pathlib import Path

from app.models.jobs import SeenJobEntry
from app.storage.job_repository import JobRepository


def test_job_repository_incremental_upsert(tmp_path):
    path = tmp_path / "seen_jobs.json"
    repo = JobRepository(path)
    repo.upsert(
        "https://a.com",
        SeenJobEntry(
            title="T",
            company="C",
            url="https://a.com",
            first_seen="2026-06-10",
            fit="high",
            status="new",
        ),
    )
    repo.flush()
    repo.invalidate()
    repo2 = JobRepository(path)
    assert len(repo2.all()) == 1
    assert repo2.update_fields("https://a.com", status="skipped")
    repo2.flush()
    data = json.loads(path.read_text())
    assert data["seen"]["https://a.com"]["status"] == "skipped"
