"""Assistant tool registry — whitelist and guardrails."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.services.assistant.tool_registry import BLOCKED_TOOL_NAMES, ToolRegistry
from app.storage.job_repository import JobRepository


def _settings(tmp_path: Path) -> Settings:
    scraper_dir = tmp_path / "job_scraper"
    scraper_dir.mkdir(parents=True)
    seen_path = scraper_dir / "seen_jobs.json"
    seen_path.write_text(
        json.dumps(
            {
                "seen": {
                    "https://example.com/new-job": {
                        "title": "Dev",
                        "company": "Acme",
                        "url": "https://example.com/new-job",
                        "first_seen": "2026-06-09",
                        "status": "new",
                        "fit": "high",
                    },
                    "https://example.com/eval-job": {
                        "title": "Ops",
                        "company": "Beta",
                        "url": "https://example.com/eval-job",
                        "first_seen": "2026-06-09",
                        "status": "evaluated",
                        "fit": "high",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return Settings().model_copy(update={"data_dir": tmp_path.resolve()})


@pytest.mark.asyncio
async def test_blocked_tools_not_in_registry():
    reg = ToolRegistry()
    for name in BLOCKED_TOOL_NAMES:
        assert not reg.is_allowed(name)


@pytest.mark.asyncio
async def test_read_tools_allowed():
    reg = ToolRegistry()
    for name in (
        "get_health",
        "get_inbox_counts",
        "list_inbox_jobs",
        "list_applications",
        "get_setup_state",
    ):
        assert reg.is_allowed(name)


@pytest.mark.asyncio
async def test_skip_evaluated_job_blocked(tmp_path):
    settings = _settings(tmp_path)
    reg = ToolRegistry(settings)
    result = await reg.execute(
        "skip_inbox_job",
        {"url": "https://example.com/eval-job", "reason": "test"},
    )
    assert result["ok"] is False
    assert "evaluated" in result["error"].lower()


@pytest.mark.asyncio
async def test_skip_new_job_ok(tmp_path):
    settings = _settings(tmp_path)
    reg = ToolRegistry(settings)
    result = await reg.execute(
        "skip_inbox_job",
        {"url": "https://example.com/new-job", "reason": "asystent test"},
    )
    assert result["ok"] is True
    assert result["result"]["skipped"] is True
    repo = JobRepository(settings.seen_jobs_path)
    found = repo.get_by_url("https://example.com/new-job")
    assert found
    assert found[1].status == "skipped"


@pytest.mark.asyncio
async def test_confirm_required_without_confirm(tmp_path):
    settings = _settings(tmp_path)
    reg = ToolRegistry(settings)
    result = await reg.execute("start_full_apply", {"url": "https://example.com/x"})
    assert result.get("needs_confirm") is True


@pytest.mark.asyncio
async def test_unknown_tool_rejected():
    reg = ToolRegistry()
    result = await reg.execute("run_shell", {"cmd": "rm -rf /"})
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_get_inbox_counts(tmp_path):
    settings = _settings(tmp_path)
    (settings.job_scraper_dir / "triage_result.json").write_text(
        json.dumps({"ranked": [], "priority_count": 0, "review_count": 0, "skipped_count": 0}),
        encoding="utf-8",
    )
    reg = ToolRegistry(settings)
    result = await reg.execute("get_inbox_counts", {})
    assert result["ok"] is True
    assert "inbox_badge" in result["result"] or isinstance(result["result"], dict)
