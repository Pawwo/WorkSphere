"""Tests for HTML CV builder."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.services.cv.draft import baseline_cv_draft
from app.services.cv.html_builder import build_cv_html, format_contact_html
from app.services.cv.identity import parse_identity
from app.services.cv.renderer_factory import get_document_renderer, get_pdf_compiler


@pytest.fixture
def wizard_cv_text():
    state = json.loads(Path("data/setup/wizard_state.json").read_text(encoding="utf-8"))
    return state["cv_text"]


def test_format_contact_html_linkedin():
    html = format_contact_html(
        {
            "location": "Szczecin",
            "phone": "+48 601",
            "email": "test@example.com",
            "linkedin": "https://www.linkedin.com/in/test",
        }
    )
    assert "Szczecin" in html
    assert 'href="https://www.linkedin.com/in/test"' in html
    assert "LinkedIn" in html


def test_build_cv_html_matches_reference_structure(wizard_cv_text):
    settings = Settings()
    profile_md = Path("data/profile/01-candidate-profile.md").read_text(encoding="utf-8")
    draft = baseline_cv_draft(
        role="Chief Operating Officer ( COO )",
        company="UltaHost",
        profile_md=profile_md,
        language="en",
        settings=settings,
    )
    identity = parse_identity(profile_md)
    html = build_cv_html(draft, identity, "ultahost", profile_md=profile_md)

    assert "<!DOCTYPE html>" in html
    assert 'font-size: 10.5pt' in html
    assert 'line-height: 1.45' in html
    assert 'border-bottom: 3px solid #1a365d' in html
    assert '<section id="summary">' in html
    assert "<h2>Professional Summary</h2>" in html
    assert '<section id="skills">' in html
    assert 'class="skills-list"' in html
    assert "built-in method items" not in html
    assert "Executive Leadership:" in html or "Operational" in html
    assert '<section id="experience">' in html
    assert "<article>" in html
    assert "margin-bottom: 3px" in html
    assert "\\cvjob" not in html
    assert "\\documentclass" not in html
    assert "Zarządzanie całością" not in html


def test_renderer_factory_latex_default():
    settings = Settings()
    settings = settings.model_copy(update={"cv_renderer": "latex"})
    renderer = get_document_renderer(settings)
    assert renderer.file_extension == ".tex"
    compiler = get_pdf_compiler(settings)
    assert compiler.tools_available().get("lualatex") is not None or "lualatex" in compiler.tools_available()


def test_renderer_factory_html():
    settings = Settings()
    settings = settings.model_copy(update={"cv_renderer": "html"})
    renderer = get_document_renderer(settings)
    assert renderer.file_extension == ".html"
    compiler = get_pdf_compiler(settings)
    tools = compiler.tools_available()
    assert "playwright" in tools
