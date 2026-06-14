"""Tests for CV LaTeX typography macros."""

from app.services.cv.tex_style import cv_tex_preamble


def test_cv_preamble_uses_spacing_tokens_not_linespread():
    preamble = cv_tex_preamble("Test CV")
    assert "\\cvBodyLeading" in preamble
    assert "\\cvListLeading" in preamble
    assert "\\cvSectionBefore" in preamble
    assert "\\cvJobGap" in preamble
    assert "\\linespread" not in preamble
    assert "needspace" not in preamble
    assert "microtype" not in preamble
    assert "\\parskip}{0pt}" in preamble
    assert "itemsep=2pt" in preamble


def test_cv_skillcategory_uses_hangindent_not_minipage():
    preamble = cv_tex_preamble("Test CV")
    assert "\\hangindent" in preamble
    assert "\\cvskillcategory" in preamble
    assert "minipage" not in preamble.split("\\cvskillcategory")[1].split("\\newcommand")[0]


def test_cv_job_uses_nopagebreak_not_needspace():
    preamble = cv_tex_preamble("Test CV")
    job_macro = preamble.split("\\newcommand{\\cvjob}")[1].split("\\newcommand")[0]
    assert "\\nopagebreak" in job_macro
    assert "needspace" not in job_macro
