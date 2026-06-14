"""Smoke tests — integration tests hit /health with live LLM/SearXNG when not in CI."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.integration
def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ("ok", "degraded", "error")
    assert "llm" in data
    assert "searxng" in data


@pytest.mark.integration
def test_dashboard():
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "health" in data
    assert "profile" in data


def test_tools_llm_settings():
    r = client.get("/api/tools/llm")
    assert r.status_code == 200
    data = r.json()
    assert "base_url" in data
    assert "presets" in data
    assert "model" in data
    assert "api_key_set" in data
    assert "is_local_bielik" in data
    preset_ids = {p["id"] for p in data["presets"]}
    assert "8006" in preset_ids
    assert "openrouter" in preset_ids


def test_setup_status():
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    assert "complete" in r.json()


def test_documents_list():
    r = client.get("/api/documents")
    assert r.status_code == 200
    assert "categories" in r.json()


def test_pages_load():
    for path in (
        "/",
        "/inbox",
        "/tracker",
        "/dashboard",
        "/setup",
        "/apply",
        "/scrape",
        "/tools",
        "/documents",
        "/profile",
    ):
        r = client.get(path)
        assert r.status_code == 200, path


def test_jobs_redirects_to_inbox_table():
    r = client.get("/jobs", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/inbox?view=table"


def test_inbox_has_merged_view_controls():
    r = client.get("/inbox")
    assert r.status_code == 200
    html = r.text
    assert 'id="viewTabs"' in html
    assert 'id="fTier"' in html
    assert 'id="jobTableWrap"' in html
    assert "Priorytet" in html


def test_tracker_has_archived_filter():
    r = client.get("/tracker")
    assert r.status_code == 200
    assert 'value="archived"' in r.text


def test_documents_page_has_upload_zones():
    r = client.get("/documents")
    assert r.status_code == 200
    assert 'id="docGrid"' in r.text


def test_profile_page_has_file_list():
    r = client.get("/profile")
    assert r.status_code == 200
    assert 'id="fileList"' in r.text


def test_application_page_structure():
    r = client.get("/applications/999999")
    assert r.status_code == 200
    html = r.text
    assert 'id="quickEdit"' in html
    assert "Przegląd" in html
    assert "Aktywność" in html
    assert "window.__APP_ID__ = 999999" in html
    assert "window.999999" not in html


def test_shell_loads_modular_assets():
    r = client.get("/inbox")
    html = r.text
    assert "/static/css/tokens.css" in html
    assert "/static/js/core.js" in html
    assert "/static/js/inbox.js" in html
    assert "window.I18N" in html


def test_scrape_batch_preview():
    r = client.get("/api/scrape/batch/preview")
    assert r.status_code == 200
    data = r.json()
    assert "queries" in data
    assert "count" in data
    assert isinstance(data["queries"], list)


def test_scrape_async_creates_task():
    r = client.post(
        "/api/scrape/async",
        json={"query": "test", "limit": 1, "portals": ["justjoin"]},
    )
    assert r.status_code == 200
    data = r.json()
    assert "task_id" in data
    task_id = data["task_id"]
    status = client.get(f"/api/tasks/{task_id}")
    assert status.status_code == 200
    assert status.json()["kind"] == "scrape"


@pytest.mark.integration
def test_health_scrapers_per_portal():
    r = client.get("/health")
    assert r.status_code == 200
    scrapers = r.json().get("scrapers", {})
    assert "portals" in scrapers


@pytest.mark.integration
def test_scrape_response_includes_portal_errors_field():
    r = client.post(
        "/api/scrape",
        json={"query": "nonexistent-xyz-query", "limit": 1, "portals": ["pracuj"], "days": 7},
    )
    if r.status_code == 200:
        data = r.json()
        assert "portal_errors" in data
        assert isinstance(data["portal_errors"], list)
