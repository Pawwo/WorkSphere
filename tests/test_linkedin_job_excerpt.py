"""LinkedIn job body extraction and excerpt quality."""

import json
from pathlib import Path

from app.services.apply_prompt_utils import job_posting_excerpt
from app.services.job_fetcher import extract_linkedin_job_body

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SEARGIN_PARSED = Path(__file__).resolve().parents[1] / "data/applications/seargin/parsed.json"


def test_extract_linkedin_job_body_skips_cookie_banner():
    raw = (FIXTURES / "linkedin_seargin_raw.txt").read_text(encoding="utf-8")
    body = extract_linkedin_job_body(raw)
    assert "cookie" not in body[:400].lower()
    assert "Requirements" in body or "IS HIRING" in body


def test_job_posting_excerpt_has_requirements_not_cookies():
    if SEARGIN_PARSED.exists():
        raw = json.loads(SEARGIN_PARSED.read_text(encoding="utf-8"))["raw_text"]
    else:
        raw = (FIXTURES / "linkedin_seargin_raw.txt").read_text(encoding="utf-8")
    excerpt = job_posting_excerpt(raw, max_chars=600)
    assert "cookie" not in excerpt.lower()
    assert "prywatność" not in excerpt.lower()
    assert "Requirements" in excerpt or "Essential Qualifications" in excerpt
