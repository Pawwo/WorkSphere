"""Tests for job posting parse — LinkedIn PL, HTML entities."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.services.job_fetcher import (
    _enrich_linkedin_raw_text,
    _linkedin_body_usable,
    _looks_like_sentence_role,
    _manual_seen_posting,
    _parse_linkedin,
    _resolve_job_language,
    _role_from_linkedin_url,
    decode_html_entities,
    _merge_job_fields,
    fetch_job_posting,
)


def test_decode_html_entities_double_amp():
    assert decode_html_entities("A &amp;amp; B") == "A & B"
    assert decode_html_entities("Head of Ops &amp; Digital") == "Head of Ops & Digital"


def test_parse_linkedin_polish_zatrudnia():
    html = (
        '<meta property="og:title" content="'
        "Kuchnia Vikinga zatrudnia na stanowisko Head of Operations Technology &amp; Digital Transformation (m/f) w Białystok"
        ' | LinkedIn" />'
    )
    company, role, location = _parse_linkedin(html, "https://linkedin.com/jobs/view/x")
    assert company == "Kuchnia Vikinga"
    assert role == "Head of Operations Technology & Digital Transformation (m/f)"
    assert location == "Białystok"


def test_parse_linkedin_english_hiring():
    html = '<meta property="og:title" content="Acme hiring Software Engineer | LinkedIn" />'
    company, role, _ = _parse_linkedin(html, "")
    assert company == "Acme"
    assert role == "Software Engineer"


def test_role_from_linkedin_url():
    url = (
        "https://pl.linkedin.com/jobs/view/"
        "head-of-operations-technology-digital-transformation-m-f-at-kuchnia-vikinga-4425480666"
    )
    role = _role_from_linkedin_url(url)
    assert "operations" in role.lower()
    assert "kuchnia" not in role.lower()


def test_looks_like_sentence_role():
    assert _looks_like_sentence_role(
        "Kuchnia Vikinga zatrudnia na stanowisko Head of Operations w Białystok"
    )
    assert not _looks_like_sentence_role("Head of Operations Technology & Digital Transformation (m/f)")


def test_merge_prefers_seen_over_bad_linkedin():
    company, role, loc = _merge_job_fields(
        seen=("Kuchnia Vikinga", "Head of Operations (m/f)", "Białystok"),
        json_ld=(None, None, None),
        linkedin=(
            "Kuchnia Vikinga",
            "Kuchnia Vikinga zatrudnia na stanowisko Head of Operations w Białystok",
            None,
        ),
        url="https://pl.linkedin.com/jobs/view/head-of-operations-at-kuchnia-vikinga-4425480666",
    )
    assert company == "Kuchnia Vikinga"
    assert role == "Head of Operations (m/f)"
    assert loc == "Białystok"


def _settings_with_seen(tmp_path: Path) -> Settings:
    scraper = tmp_path / "job_scraper"
    scraper.mkdir(parents=True)
    (scraper / "seen_jobs.json").write_text(
        json.dumps(
            {
                "seen": {
                    "acme corp|head of operations": {
                        "title": "Head of Operations",
                        "company": "Acme Corp",
                        "url": "",
                        "description": "Head of Operations at Acme Corp. ERP Odoo transformation.",
                        "first_seen": "2026-06-11",
                        "fit": "medium",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return Settings().model_copy(update={"data_dir": tmp_path.resolve(), "repo_root": tmp_path.resolve()})


def test_manual_seen_posting_resolves_inbox_key(tmp_path):
    settings = _settings_with_seen(tmp_path)
    raw, source, seen = _manual_seen_posting(settings, "acme corp|head of operations")
    assert source == "text"
    assert "Odoo" in raw
    assert seen[0] == "Acme Corp"
    assert seen[1] == "Head of Operations"


def test_linkedin_chrome_only_not_usable():
    chrome = (
        "Poziom w hierarchii Kadra średniego szczebla Forma zatrudnienia Pełny etat "
        "Funkcja Inżynieria i Technologie informatyczne Zaloguj się Nie pamiętam hasła"
    )
    assert not _linkedin_body_usable(chrome)


def test_linkedin_enrich_from_seen_jobs(tmp_path):
    scraper = tmp_path / "job_scraper"
    scraper.mkdir(parents=True)
    url = "https://pl.linkedin.com/jobs/view/agentic-ai-automation-consultant-at-ciklum-4417752503"
    desc = (
        "Modern Automation Expertise: Proven experience in AI engineering and "
        "intelligent workflow automation. Strong hands-on experience with n8n."
    )
    (scraper / "seen_jobs.json").write_text(
        json.dumps(
            {
                "seen": {
                    url: {
                        "title": "Agentic AI & Automation Consultant",
                        "company": "Ciklum",
                        "url": url,
                        "description": desc,
                        "first_seen": "2026-06-12",
                        "fit": "medium",
                        "portal": "linkedin-pl",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    settings = Settings().model_copy(update={"data_dir": tmp_path.resolve(), "repo_root": tmp_path.resolve()})
    chrome = "Poziom w hierarchii Kadra średniego szczebla Zaloguj się"
    enriched = _enrich_linkedin_raw_text(chrome, html_text="", url=url, settings=settings)
    assert "automation" in enriched.lower()
    assert "n8n" in enriched.lower()


def test_resolve_job_language_english_role_over_chrome_pl():
    chrome = "Poziom w hierarchii Kadra średniego szczebla"
    assert _resolve_job_language("Agentic AI & Automation Consultant", chrome) == "en"


@pytest.mark.asyncio
async def test_fetch_job_posting_from_inbox_key(tmp_path):
    settings = _settings_with_seen(tmp_path)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("app.services.job_fetcher.get_settings", lambda: settings)
        parsed = await fetch_job_posting(url="acme corp|head of operations")
    assert parsed.company == "Acme Corp"
    assert parsed.role == "Head of Operations"
    assert parsed.source == "text"
