"""Unit tests for verification checklist heuristic fixes."""

from app.models.apply import FitEvaluation, JobParsed, ReviewerResult
from app.services.cv.competencies import _role_keywords_present
from app.services.verification_service import (
    _cover_mentions_company,
    _is_llm_degraded,
    run_verification_checklist,
)


def test_role_mentioned_uses_meaningful_tokens_not_acronym_only():
    job = JobParsed(
        company="Coloplast",
        role="CPBC Global Operations Director",
        location="Szczecin",
        language="en",
        raw_text="operations director",
        source="url",
    )
    cv = (
        '<section id="summary"><p>Operations Director with global delivery experience.</p></section>'
    )
    assert _role_keywords_present(cv, job.role) is True

    job = JobParsed(
        company="Wolters Kluwer Polska Sp. z o.o.",
        role="Project Manager",
        location="Warsaw",
        language="en",
        raw_text="project management",
        source="url",
    )
    cover = "<p>Dear Hiring Manager,</p><p>I am applying to Wolters Kluwer Polska.</p>"
    assert _cover_mentions_company(job, cover) is True


def test_is_llm_degraded_detects_fallback():
    assert _is_llm_degraded(["LLM fallback: offline baseline, skipped 4 tailor calls."])
    assert not _is_llm_degraded(["ATS enrichment: PM summary"])


def test_posting_keywords_skipped_for_chrome_only():
    job = JobParsed(
        company="Ciklum",
        role="Project Manager",
        location="Remote",
        language="en",
        raw_text="Poziom w hierarchii kadra średniego szczebla forma zatrudnienia pełny etat",
        source="url",
    )
    cv_html = (
        "<!DOCTYPE html><html><body>"
        '<section id="summary"><p>Project Manager with delivery experience.</p></section>'
        '<section id="skills"><ul><li>Agile</li></ul></section>'
        '<section id="experience"><ul><li>Managed teams.</li></ul></section>'
        '<section id="education"><p>MBA</p></section>'
        "</body></html>"
    )
    cover = "<div class='cover-letter'><p>Dear Team at Ciklum,</p></div>"
    result = run_verification_checklist(
        job=job,
        cv_tex=cv_html,
        cover_tex=cover,
        profile_md="- **Email:** test@example.com",
        evaluation=FitEvaluation(overall_fit="moderate", recommendation="apply"),
        reviewer=ReviewerResult(),
        pdf_files=[],
        pdf_checks=[],
        renderer="html",
        job_targets={},
    )
    kw_item = next(
        i
        for i in result["items"]
        if i["label"].startswith("Posting keywords reflected")
    )
    assert kw_item["pass"] is True
    assert "chrome-only" in kw_item.get("note", "")


def test_enrich_summary_lead_weaves_opening():
    from app.services.cv.ats_enrichment import enrich_summary_lead_keywords

    summary = "COO with 15+ years leading delivery organizations."
    targets = {
        "must_have_keywords": [
            "project management",
            "stakeholder engagement",
            "data analysis",
        ]
    }
    out = enrich_summary_lead_keywords(summary, targets, language="en", min_count=2)
    assert out.startswith("Experienced in")
    assert "project management" in out[:400].lower()
    assert "stakeholder engagement" in out[:400].lower()


def test_bullet_quality_skipped_when_llm_degraded():
    job = JobParsed(
        company="Acme",
        role="COO",
        location="PL",
        language="pl",
        raw_text="operations management",
        source="url",
    )
    cv_html = (
        "<!DOCTYPE html><html><body>"
        '<section id="summary"><p>COO z doświadczeniem operacyjnym.</p></section>'
        '<section id="skills"><ul><li>Leadership</li></ul></section>'
        '<section id="experience"><ul><li>Zarządzanie operacjami firmy.</li></ul></section>'
        '<section id="education"><p>MBA</p></section>'
        "</body></html>"
    )
    result = run_verification_checklist(
        job=job,
        cv_tex=cv_html,
        cover_tex="<div class='cover-letter'><p>Szanowni Państwo,</p></div>",
        profile_md="",
        evaluation=FitEvaluation(overall_fit="moderate", recommendation="apply"),
        reviewer=ReviewerResult(),
        pdf_files=[],
        pdf_checks=[],
        renderer="html",
        tailoring_decisions=["LLM fallback: offline baseline, skipped 4 tailor calls."],
    )
    bullet_item = next(
        i for i in result["items"] if i["label"].startswith("Bullet quality")
    )
    assert bullet_item["pass"] is True
    assert "skipped" in bullet_item.get("note", "").lower()
