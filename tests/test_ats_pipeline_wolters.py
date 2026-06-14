"""End-to-end ATS checks for Wolters #41-style Project & Program Manager posting."""

import json
from pathlib import Path

from app.config import Settings
from app.services.cv.identity import parse_identity
from app.models.apply import FitEvaluation, JobParsed, ReviewerResult
from app.services.cv.ats_enrichment import apply_pm_ats_enrichment, normalize_job_targets
from app.services.cv.ats_scoring import (
    ats_keyword_coverage,
    bullet_quality_ratio,
    experience_bullets_from_html,
    html_to_plain_text,
)
from app.services.cv.draft import baseline_cv_draft
from app.services.cv.html_builder import build_cv_html
from app.services.cv.truth_guard import build_skill_truth_index
from app.services.verification_service import run_verification_checklist
from tests.conftest import CANDIDATE_PROFILE, WOLTERS_APP_DIR, WOLTERS_CV_HTML


WOLTERS_TARGETS = {
    "role_title": "Project & Program Manager",
    "must_have_keywords": [
        "JIRA",
        "Confluence",
        "project management",
        "stakeholder engagement",
        "Agile",
        "project lifecycle",
    ],
    "tools_explicit": ["JIRA", "Confluence"],
    "nice_to_have_keywords": ["Scrum", "Waterfall"],
    "priority_themes": ["stakeholder management", "project delivery"],
    "emphasis_jobs": ["Chief Operating Officer"],
    "profile_angle": "PM with JIRA and stakeholder engagement",
    "avoid_framing": ["software developer"],
}


def _wolters_job() -> JobParsed:
    parsed = json.loads((WOLTERS_APP_DIR / "parsed.json").read_text(encoding="utf-8"))
    return JobParsed(**parsed)


def test_config_loads_ats_section():
    settings = Settings()
    assert settings.ats_min_keyword_coverage == 0.70
    assert settings.ats_bold_keywords_in_bullets is True
    assert settings.ats_truth_guard_strict is True
    assert settings.ats_max_experience_llm_batches == 2


def test_wolters_cv_truth_guard_and_keyword_coverage():
    profile_md = CANDIDATE_PROFILE.read_text(encoding="utf-8")
    job = _wolters_job()
    settings = Settings()
    draft = baseline_cv_draft(
        role=job.role,
        company=job.company,
        profile_md=profile_md,
        language="en",
        settings=settings,
    )
    draft.profile_statement = (
        "Project and Program Manager with hands-on JIRA and Confluence experience, "
        "stakeholder engagement, and Agile project lifecycle delivery."
    )
    truth = build_skill_truth_index(profile_md=profile_md, settings=settings)
    contaminated, violations = truth.sanitize_text(
        "Delivered SAP ERP rollout and Zapier workflow automation."
    )
    assert violations
    assert "zapier" not in contaminated.lower()
    assert "sap" not in contaminated.lower()

    if draft.experience_entries:
        draft.experience_entries[0].bullets = [
            contaminated,
            "Led project management with JIRA dashboards, Confluence playbooks, and stakeholder engagement.",
        ]

    identity = parse_identity(profile_md)
    html = build_cv_html(
        draft,
        identity,
        profile_md=profile_md,
        job_targets=WOLTERS_TARGETS,
        highlight_keywords=True,
    )
    plain = html_to_plain_text(html).lower()
    assert "zapier" not in plain
    assert "sap erp" not in plain and "sap s/4hana" not in plain
    assert "jira" in plain or "project management" in plain

    coverage = ats_keyword_coverage(WOLTERS_TARGETS, plain)
    assert coverage["coverage_ratio"] >= 0.70, coverage


def test_wolters_enriched_draft_passes_ats_heuristics():
    profile_md = CANDIDATE_PROFILE.read_text(encoding="utf-8")
    job = _wolters_job()
    settings = Settings()
    truth = build_skill_truth_index(profile_md=profile_md, settings=settings)
    targets = normalize_job_targets(
        dict(WOLTERS_TARGETS),
        job=job,
        truth=truth,
        profile_md=profile_md,
    )
    draft = baseline_cv_draft(
        role=job.role,
        company=job.company,
        profile_md=profile_md,
        language="en",
        settings=settings,
    )
    summary, comps, exp, notes = apply_pm_ats_enrichment(
        profile_statement=draft.profile_statement,
        competencies=draft.competencies,
        experience_entries=draft.experience_entries[:6],
        job=job,
        profile_md=profile_md,
        job_targets=targets,
        truth=truth,
    )
    assert any("ATS enrichment" in n for n in notes)
    draft.profile_statement = summary
    draft.competencies = comps
    draft.experience_entries = exp
    html = build_cv_html(
        draft,
        parse_identity(profile_md),
        profile_md=profile_md,
        job_targets=targets,
        highlight_keywords=True,
    )
    plain = html_to_plain_text(html).lower()
    coverage = ats_keyword_coverage(targets, plain)
    assert coverage["coverage_ratio"] >= 0.70, coverage

    summary_m = html.lower().split("<section id=\"summary\">", 1)[-1]
    lead = summary_m[:600]
    kw_hits = sum(
        1
        for k in (targets.get("must_have_keywords") or [])[:8]
        if str(k).lower() in lead
    )
    assert kw_hits >= 2, f"summary lead keywords: {kw_hits}"

    assert bullet_quality_ratio(experience_bullets_from_html(html)) >= 0.6


def test_wolters_verification_includes_ats_score():
    profile_md = CANDIDATE_PROFILE.read_text(encoding="utf-8")
    job = _wolters_job()
    identity = parse_identity(profile_md)
    cv_path = WOLTERS_CV_HTML
    cv_html = cv_path.read_text(encoding="utf-8")
    eval_path = WOLTERS_APP_DIR / "evaluation.json"
    ev = FitEvaluation(**json.loads(eval_path.read_text(encoding="utf-8")))

    result = run_verification_checklist(
        job=job,
        cv_tex=cv_html,
        cover_tex='<html><body class="cover-letter"><p>Dear Hiring Manager,</p></body></html>',
        profile_md=profile_md,
        evaluation=ev,
        reviewer=ReviewerResult(),
        pdf_files=[],
        pdf_checks=[],
        renderer="html",
        job_targets=WOLTERS_TARGETS,
    )

    assert "ats_score" in result
    assert isinstance(result["ats_score"], int)
    assert "keyword_coverage" in result
    ats_labels = [i["label"] for i in result["items"] if i["category"] == "ats"]
    assert any("Keyword coverage" in label for label in ats_labels)
    assert any("Truth guard" in label for label in ats_labels)
