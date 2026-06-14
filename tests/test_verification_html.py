"""Verification checklist for HTML CV/cover documents."""

import json
from pathlib import Path

from app.config import Settings
from app.models.apply import FitEvaluation, JobParsed, ReviewerResult
from app.services.cv.html_builder import build_cover_html
from app.services.cv.identity import parse_identity
from app.services.cv.language import localize_identity
from app.services.cv.tex_parser import parse_cover_tex
from app.services.verification_service import detect_renderer_format, run_verification_checklist
from tests.conftest import CANDIDATE_PROFILE, FIXTURES_DIR, WOLTERS_APP_DIR, WOLTERS_CV_HTML

WOLTERS_COVER_TEX = FIXTURES_DIR / "cover" / "wolters_sample.tex"


def test_detect_renderer_format_html():
    assert detect_renderer_format("<!DOCTYPE html><html>", "", "auto") == "html"
    assert detect_renderer_format("\\documentclass{extarticle}", "", "auto") == "latex"


def test_parse_cover_tex_wolters():
    tex = WOLTERS_COVER_TEX.read_text(encoding="utf-8")
    data = parse_cover_tex(tex)
    assert data["salutation"] == "Dear Hiring Manager,"
    assert "Wolters Kluwer" in data["opening"]
    assert len(data["bullets"]) == 3
    assert "20%" in data["bullets"][1]


def test_html_verification_wolters_passes_without_latex_checks(tmp_path):
    parsed = json.loads((WOLTERS_APP_DIR / "parsed.json").read_text(encoding="utf-8"))
    eval_data = json.loads((WOLTERS_APP_DIR / "evaluation.json").read_text(encoding="utf-8"))
    job = JobParsed(**parsed)
    profile_md = CANDIDATE_PROFILE.read_text(encoding="utf-8")
    identity = localize_identity(parse_identity(profile_md), job.language)
    cv_html = WOLTERS_CV_HTML.read_text(encoding="utf-8")
    cover_data = parse_cover_tex(WOLTERS_COVER_TEX.read_text(encoding="utf-8"))
    cover_html = build_cover_html(cover_data, identity)
    cv_pdf = tmp_path / "cv.pdf"
    cover_pdf = tmp_path / "cover.pdf"
    cv_pdf.write_bytes(b"%PDF-1.4 test")
    cover_pdf.write_bytes(b"%PDF-1.4 test")

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
