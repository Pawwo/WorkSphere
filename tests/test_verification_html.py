"""Verification checklist for HTML CV/cover documents."""

import json
from pathlib import Path

from app.config import Settings
from app.models.apply import FitEvaluation, JobParsed, ReviewerResult
from app.services.apply_service import application_cover_filename, application_cv_filename
from app.services.cv.html_builder import build_cover_html
from app.services.cv.identity import parse_identity
from app.services.cv.language import localize_identity
from app.services.cv.tex_parser import parse_cover_tex
from app.services.verification_service import detect_renderer_format, run_verification_checklist


def test_detect_renderer_format_html():
    assert detect_renderer_format("<!DOCTYPE html><html>", "", "auto") == "html"
    assert detect_renderer_format("\\documentclass{extarticle}", "", "auto") == "latex"


def test_parse_cover_tex_wolters():
    tex = Path(
        "cover_letters/cover_wolters_kluwer_polska_sp_z_oo_project_program_manager.tex"
    ).read_text(encoding="utf-8")
    data = parse_cover_tex(tex)
    assert data["salutation"] == "Dear Hiring Manager,"
    assert "Wolters Kluwer" in data["opening"]
    assert len(data["bullets"]) == 3
    assert "20%" in data["bullets"][1]


def test_html_verification_wolters_passes_without_latex_checks():
    settings = Settings()
    parsed = json.loads(
        (settings.data_dir / "applications/wolters_kluwer_polska_sp_z_oo/parsed.json").read_text()
    )
    eval_data = json.loads(
        (settings.data_dir / "applications/wolters_kluwer_polska_sp_z_oo/evaluation.json").read_text()
    )
    job = JobParsed(**parsed)
    profile_md = Path("data/profile/01-candidate-profile.md").read_text(encoding="utf-8")
    identity = localize_identity(parse_identity(profile_md), job.language)
    cv_path = Path("cv") / application_cv_filename(identity["name"], job.company, ".html")
    if not cv_path.exists():
        cv_path = Path("cv/main_wolters_kluwer_polska_sp_z_oo.html")
    cv_html = cv_path.read_text(encoding="utf-8")
    tex = Path(
        "cover_letters/cover_wolters_kluwer_polska_sp_z_oo_project_program_manager.tex"
    ).read_text(encoding="utf-8")
    cover_data = parse_cover_tex(tex)
    cover_html = build_cover_html(cover_data, identity)
    cover_pdf = Path("cover_letters") / application_cover_filename(
        identity["name"], job.company, ".pdf"
    )
    if not cover_pdf.exists():
        cover_pdf = Path(
            "cover_letters/cover_wolters_kluwer_polska_sp_z_oo_project_program_manager.pdf"
        )
    cv_pdf = cv_path.with_suffix(".pdf")
    if not cv_pdf.exists():
        cv_pdf = Path("cv/main_wolters_kluwer_polska_sp_z_oo.pdf")

    job_targets = {
        "must_have_keywords": [
            "project management",
            "stakeholder engagement",
            "digital transformation",
            "Project",
        ],
    }
    result = run_verification_checklist(
        job=job,
        cv_tex=cv_html,
        cover_tex=cover_html,
        profile_md=profile_md,
        evaluation=FitEvaluation(**eval_data),
        reviewer=ReviewerResult(),
        pdf_files=[str(cv_pdf), str(cover_pdf)],
        pdf_checks=["pass: CV 2 stron", "pass: List 1 stron"],
        renderer="html",
        job_targets=job_targets,
    )

    labels = {item["label"] for item in result["items"]}
    assert "Balanced LaTeX braces in CV" not in labels
    assert "Balanced LaTeX braces in cover" not in labels
    assert "ats_score" in result
    assert any(item["category"] == "ats" for item in result["items"])
    assert result["all_pass"] is True
    assert result["passed"] == result["total"]
