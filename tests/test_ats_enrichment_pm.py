"""Tests for PM ATS deterministic enrichment."""

import json
from pathlib import Path

from app.config import Settings, get_settings
from app.models.apply import FitEvaluation, JobParsed, ReviewerResult
from app.services.cv.ats_enrichment import (
    apply_pm_ats_enrichment,
    enrich_summary_for_pm,
    is_pm_role,
    normalize_job_targets,
    years_experience_from_profile,
)
from app.services.cv.ats_scoring import bullet_quality_ratio, html_to_plain_text
from app.services.cv.draft import baseline_cv_draft
from app.services.cv.html_builder import build_cv_html
from app.services.cv.identity import parse_identity
from app.services.cv.truth_guard import SkillTruthIndex, build_skill_truth_index
from app.services.cv.types import ExperienceEntry
from app.services.verification_service import run_verification_checklist
from tests.conftest import CANDIDATE_PROFILE, WOLTERS_APP_DIR

WOLTERS_TARGETS = {
    "role_title": "Project & Program Manager",
    "must_have_keywords": [
        "project schedules",
        "budgets",
        "stakeholder engagement",
        "managing projects",
        "JIRA",
        "Confluence",
        "Agile",
    ],
    "tools_explicit": ["JIRA", "Confluence"],
    "soft_skills": ["stakeholder engagement", "project management"],
    "keyword_placement_hints": {
        "summary": ["stakeholder engagement", "JIRA"],
        "top_bullets": ["project schedules", "budgets"],
    },
}

PROFILE = CANDIDATE_PROFILE.read_text(encoding="utf-8")


def test_is_pm_role():
    assert is_pm_role("Project & Program Manager")
    assert not is_pm_role("Chief Operating Officer")


def test_years_from_profile():
    years = years_experience_from_profile(PROFILE)
    assert years is not None
    assert years >= 5


def test_normalize_job_targets_merges_tools():
    truth = build_skill_truth_index(profile_md=PROFILE)
    job = JobParsed(
        company="Wolters",
        role="Project & Program Manager",
        raw_text="Technologies we use Expected Jira Confluence Agile Scrum project lifecycle",
        language="en",
    )
    raw = {
        "must_have_keywords": ["managing projects"],
        "tools_explicit": ["JIRA", "Confluence"],
        "normalized_skills": [
            {"posting_term": "managing projects", "candidate_term": "founder / co"},
        ],
        "keyword_placement_hints": {"summary": ["English B1+"]},
    }
    out = normalize_job_targets(raw, job=job, truth=truth, profile_md=PROFILE)
    must = [k.lower() for k in out["must_have_keywords"]]
    assert any("jira" in k for k in must)
    assert "English" not in " ".join(out["keyword_placement_hints"]["summary"])


def test_enrich_summary_has_lead_keywords():
    truth = build_skill_truth_index(profile_md=PROFILE)
    summary = enrich_summary_for_pm(
        "Generic professional.",
        "Project & Program Manager",
        WOLTERS_TARGETS,
        PROFILE,
        truth,
        min_lead_keywords=2,
    )
    low = summary.lower()
    hits = sum(
        1
        for k in WOLTERS_TARGETS["must_have_keywords"][:6]
        if k.lower() in low or k.lower().replace(" ", "") in low.replace(" ", "")
    )
    assert "project" in low
    assert "stakeholder" in low or hits >= 2


def test_apply_pm_enrichment_coo_and_myodoo_bullets():
    truth = build_skill_truth_index(profile_md=PROFILE)
    entries = [
        ExperienceEntry(
            period="2025",
            title="Chief Operating Officer",
            company="VentorTech",
            bullets=["Oversaw operations."],
        ),
        ExperienceEntry(
            period="2025",
            title="Founder / Co-Owner",
            company="myOdoo.pl",
            bullets=["Defined product vision."],
        ),
    ]
    summary, comps, exp, notes = apply_pm_ats_enrichment(
        profile_statement="Generic summary.",
        competencies=["Executive Leadership: COO, KPI"],
        experience_entries=entries,
        job=JobParsed(company="W", role="Project & Program Manager", raw_text="JIRA Agile", language="en"),
        profile_md=PROFILE,
        job_targets=WOLTERS_TARGETS,
        truth=truth,
    )
    assert any("ATS enrichment" in n for n in notes)
    assert any("project lifecycle" in b.lower() for e in exp for b in e.bullets if "coo" in e.title.lower() or "ventor" in e.company.lower())
    assert any("agile" in b.lower() for e in exp for b in e.bullets if "myodoo" in e.company.lower())
    assert any("jira" in c.lower() or "Project & Program" in c for c in comps)
    bullets = [b for e in exp for b in e.bullets]
    assert bullet_quality_ratio(bullets) >= 0.6


def test_enriched_html_passes_summary_scan_heuristic():
    settings = Settings()
    truth = build_skill_truth_index(profile_md=PROFILE, settings=settings)
    draft = baseline_cv_draft(
        role="Project & Program Manager",
        company="Wolters",
        profile_md=PROFILE,
        language="en",
        settings=settings,
    )
    summary, comps, exp, _ = apply_pm_ats_enrichment(
        profile_statement=draft.profile_statement,
        competencies=draft.competencies,
        experience_entries=draft.experience_entries[:4],
        job=JobParsed(
            company="Wolters Kluwer",
            role="Project & Program Manager",
            raw_text=(WOLTERS_APP_DIR / "parsed.json").read_text()[:500],
            language="en",
        ),
        profile_md=PROFILE,
        job_targets=WOLTERS_TARGETS,
        truth=truth,
    )
    draft.profile_statement = summary
    draft.competencies = comps
    draft.experience_entries = exp
    html = build_cv_html(
        draft,
        parse_identity(PROFILE),
        profile_md=PROFILE,
        job_targets=WOLTERS_TARGETS,
    )
    assert "{'category'" not in html
    plain = html_to_plain_text(html).lower()
    assert "zapier" not in plain

    parsed = json.loads(
        (WOLTERS_APP_DIR / "parsed.json").read_text()
    )
    result = run_verification_checklist(
        job=JobParsed(**parsed),
        cv_tex=html,
        cover_tex='<html><body class="cover-letter"><p>Dear Hiring Manager,</p></body></html>',
        profile_md=PROFILE,
        evaluation=FitEvaluation(overall_fit="moderate", recommendation="ok"),
        reviewer=ReviewerResult(),
        pdf_files=[],
        pdf_checks=[],
        renderer="html",
        job_targets=WOLTERS_TARGETS,
    )
    ats_items = {i["label"]: i["pass"] for i in result["items"] if i["category"] == "ats"}
    assert ats_items.get("Keyword coverage ≥ 70%", False) or result.get("keyword_coverage", {}).get("coverage_ratio", 0) >= 0.7


def test_config_enrich_pm_roles():
    assert get_settings().ats_enrich_pm_roles is True
    assert get_settings().ats_summary_min_lead_keywords == 2


def test_enrich_summary_polish_not_english():
    truth = build_skill_truth_index(profile_md=PROFILE)
    targets = {
        **WOLTERS_TARGETS,
        "must_have_keywords": [
            "hybrydowy model pracy",
            "planowanie projektów",
            "analiza wymagań",
            "zarządzanie budżetem",
            "Agile",
            "JIRA",
            "Confluence",
        ],
    }
    summary = enrich_summary_for_pm(
        "Krótkie podsumowanie.",
        "Senior IT Program Manager",
        targets,
        PROFILE,
        truth,
        min_lead_keywords=2,
        language="pl",
    )
    low = summary.lower()
    assert "with " not in low
    assert "experienced managing" not in low
    assert "doświadczen" in low or "lat doświadczenia" in low
    assert "hybrydowy model pracy" in low or "planowanie projektów" in low


def test_normalize_bullet_polish_no_managed_prefix():
    from app.services.cv.ats_enrichment import _normalize_bullet

    truth = build_skill_truth_index(profile_md=PROFILE)
    out = _normalize_bullet(
        "zarządzałem całością operacji firmy",
        truth,
        language="pl",
    )
    assert not out.lower().startswith("managed ")
    assert "zarządzałem" in out.lower()
