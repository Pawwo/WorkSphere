"""Tests for LLM CV tailoring service."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models.apply import JobParsed
from app.services.apply_prompt_utils import safe_max_tokens
from app.services.cv_builder import CvDraftData, ExperienceEntry, baseline_cv_draft
from app.services.cv_tailor_service import CvTailorError, CvTailorService

JOB = JobParsed(
    company="Kuchnia Vikinga",
    role="Head of Operations Technology",
    raw_text=(
        "Head of Operations Technology & Digital Transformation. "
        "Requirements: Odoo ERP, KPI, P&L, team leadership, digital transformation, CI/CD."
    ),
    language="en",
)

TARGETS_JSON = """{
  "role_title": "Head of Operations Technology",
  "must_have_keywords": ["Odoo ERP", "KPI", "digital transformation", "team leadership"],
  "nice_to_have_keywords": ["CI/CD"],
  "priority_themes": ["operations", "ERP"],
  "emphasis_jobs": ["Chief Operating Officer"],
  "profile_angle": "COO with Odoo and transformation experience",
  "avoid_framing": ["python developer"]
}"""

HEADER_JSON = """{
  "profile_statement": "Operations leader with Odoo ERP and digital transformation track record.",
  "competency_keywords": ["digital transformation"],
  "competencies": ["UltaHost: UltaHost", "COO: COO"],
  "tailoring_notes": ["Lead with operations fit"]
}"""

CV_JSON = """{
  "experience_entries": [{
    "period": "08.2025--Present",
    "title": "Chief Operating Officer",
    "company": "VentorTech",
    "location": "Szczecin",
    "bullets": ["Led Odoo delivery operations and KPI dashboards aligned to digital transformation goals."]
  }],
  "tailoring_notes": ["Emphasized Odoo and KPI from posting"]
}"""

COVER_JSON = """{
  "salutation": "Dear Hiring Manager,",
  "opening": "Applying for Head of Operations Technology.",
  "body": "Odoo ERP and transformation background.",
  "bullets": ["Odoo ERP delivery", "KPI management", "Team leadership"],
  "motivation": "Interested in Kuchnia Vikinga operations scale-up.",
  "closing": "Best regards."
}"""


def test_safe_max_tokens_fits_context():
    messages = [{"role": "user", "content": "x" * 3000}]
    mt = safe_max_tokens(messages, requested=2048, n_ctx=2048)
    assert mt < 2048
    assert mt >= 96


@pytest.mark.asyncio
async def test_tailor_application_requires_llm():
    svc = CvTailorService()
    baseline = baseline_cv_draft(role=JOB.role, company=JOB.company, profile_md="## Identity\n- **Name:** Test")
    with patch.object(svc.llm, "is_ready", AsyncMock(return_value=False)):
            with pytest.raises(CvTailorError, match="wymaga działającego LLM"):
                await svc.tailor_application(
                    JOB,
                    baseline=baseline,
                    profile_md="",
                    behavioral_md="",
                    cover_default={},
                )


@pytest.mark.asyncio
async def test_tailor_application_success():
    svc = CvTailorService()
    baseline = CvDraftData(
        profile_statement="Base",
        competencies=["Ops: Odoo"],
        experience_entries=[
            ExperienceEntry(
                period="08.2025-Present",
                title="Chief Operating Officer",
                company="VentorTech",
                bullets=["Managed Odoo projects."],
            )
        ],
        education_entries=[],
    )

    responses = [CV_JSON, COVER_JSON]
    calls = {"n": 0}

    async def fake_chat(messages, max_tokens=1024, temperature=0.0):
        out = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return out

    async def passthrough_align(draft, job, **kw):
        return draft, []

    with patch.object(svc.llm, "is_ready", AsyncMock(return_value=True)):
        with patch.object(
            svc,
            "_resolve_targets",
            AsyncMock(
                return_value=(json.loads(TARGETS_JSON), json.loads(HEADER_JSON)),
            ),
        ):
            with patch.object(svc, "_align_cv_language", AsyncMock(side_effect=passthrough_align)):
                with patch.object(svc.llm, "chat_complete", AsyncMock(side_effect=fake_chat)):
                    result = await svc.tailor_application(
                    JOB,
                    baseline=baseline,
                    profile_md="## Identity\n- **Name:** Test",
                    behavioral_md="",
                    cover_default={"opening": "x"},
                )

    assert calls["n"] == 2
    assert "Odoo" in result.cv_draft.profile_statement
    assert not any(": UltaHost" in c and c.startswith("UltaHost") for c in result.cv_draft.competencies)
    assert result.job_targets.get("must_have_keywords")
    assert any("Multi-pass" in d for d in result.tailoring_decisions)
    assert result.cover_data.get("bullets")


@pytest.mark.asyncio
async def test_baseline_fallback_skips_llm_translation_on_json_fail():
    svc = CvTailorService()
    baseline = baseline_cv_draft(
        role="Project & Program Manager",
        company="Wolters Kluwer",
        profile_md="## Identity\n- **Name:** Test",
        language="en",
    )

    with patch.object(svc.llm, "is_ready", AsyncMock(return_value=True)):
        with patch.object(
            svc,
            "_resolve_targets",
            AsyncMock(side_effect=CvTailorError("LLM zwrócił niepoprawny JSON.")),
        ):
            with patch.object(
                svc,
                "_align_cv_language",
                AsyncMock(side_effect=lambda d, job, **kw: (d, [])),
            ):
                result = await svc.tailor_application_with_fallback(
                    JobParsed(
                        company="Wolters Kluwer",
                        role="Project & Program Manager",
                        raw_text="English posting about program management.",
                        language="en",
                    ),
                    baseline=baseline,
                    profile_md="## Identity\n- **Name:** Test",
                    behavioral_md="",
                    cover_default={"opening": "x"},
                )

    assert result.llm_degraded is True
    assert any("offline baseline" in d for d in result.tailoring_decisions)


def test_targets_cache_stores_header(tmp_path):
    from app.config import Settings

    settings = Settings(db_path=str(tmp_path / "app.db"), repo_root=tmp_path)
    slug = "cache_test_co"
    (settings.data_dir / "applications" / slug).mkdir(parents=True, exist_ok=True)
    svc = CvTailorService(
        settings,
        company_slug=slug,
        job_url="https://linkedin.com/jobs/view/123",
    )
    targets = {"must_have_keywords": ["Jira"], "role_title": "PM"}
    header = {
        "profile_statement": "Cached PM leader.",
        "competencies": ["Ops: Ops"],
        "competency_keywords": ["Jira"],
    }
    svc._save_targets_cache(targets, header=header)
    loaded_targets, loaded_header = svc._load_targets_cache()
    assert loaded_targets == targets
    assert loaded_header is not None
    assert loaded_header["profile_statement"] == "Cached PM leader."


def test_save_header_cache_merges_into_existing_targets(tmp_path):
    from app.config import Settings

    settings = Settings(db_path=str(tmp_path / "app.db"), repo_root=tmp_path)
    slug = "cache_test_co2"
    (settings.data_dir / "applications" / slug).mkdir(parents=True, exist_ok=True)
    svc = CvTailorService(
        settings,
        company_slug=slug,
        job_url="https://linkedin.com/jobs/view/123",
    )
    targets = {"must_have_keywords": ["Jira"]}
    svc._save_targets_cache(targets)
    svc._save_header_cache({"profile_statement": "Late header", "competencies": []})
    _, header = svc._load_targets_cache()
    assert header["profile_statement"] == "Late header"


@pytest.mark.asyncio
async def test_align_cv_language_en_uses_compact_before_full_translate():
    svc = CvTailorService()
    draft = CvDraftData(
        profile_statement="Lider operacji z Odoo.",
        competencies=["Ops: Odoo"],
        experience_entries=[
            ExperienceEntry(
                period="2020-Present",
                title="COO",
                company="Acme",
                bullets=["Zarządzał zespołem wdrożeń Odoo."],
            )
        ],
        education_entries=[],
    )
    aligned = CvDraftData(
        profile_statement="Operations leader with Odoo.",
        competencies=["Ops: Odoo"],
        experience_entries=[
            ExperienceEntry(
                period="2020-Present",
                title="COO",
                company="Acme",
                bullets=["Led Odoo implementation team."],
            )
        ],
        education_entries=[],
    )
    compact = AsyncMock(return_value=aligned)
    full = AsyncMock(side_effect=AssertionError("_translate_draft should not run"))

    with patch.object(svc, "translate_pdf_entries_only", compact):
        with patch.object(svc, "_translate_draft", full):
            result, warnings = await svc._align_cv_language(
                draft,
                JOB,
                profile_md="## Identity\n- **Name:** Test",
            )

    compact.assert_awaited_once()
    full.assert_not_awaited()
    assert "compact LLM translate" in " ".join(warnings)
    assert "Odoo" in result.profile_statement
