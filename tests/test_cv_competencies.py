"""Tests for CV competencies parsing and validation."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.services.cv.competencies import (
    is_valid_competency,
    merge_competencies,
    normalize_competency_line,
    parse_competencies_from_master,
    sanitize_competencies,
)
from app.services.cv.draft import baseline_cv_draft, cv_draft_from_llm_dict
from app.services.cv.experience import (
    ExperienceEntry,
    _period_end_key,
    resolve_experience_entries,
    select_experience_for_pdf,
)
from app.services.cv.master import resolve_master_cv_text
from app.services.cv.types import CvDraftData
from app.services.cv_builder import build_cv_tex, parse_identity

PROFILE_WITH_PLACEHOLDERS = """
## Professional Experience

### Chief Operating Officer - VentorTech (08.2025 - present)
Warszawa / Szczecin
- (uzupełnij)

### Founder / Co-Owner - myOdoo.pl sp. z o.o. (07.2025 - present)
Szczecin
- (uzupełnij)
"""


@pytest.fixture
def wizard_cv_text():
    state = json.loads(Path("data/setup/wizard_state.json").read_text(encoding="utf-8"))
    return state["cv_text"]


def test_is_valid_competency_rejects_echo():
    assert not is_valid_competency("UltaHost: UltaHost")
    assert not is_valid_competency("COO: COO")
    assert is_valid_competency(
        "Executive Leadership: COO Leadership, Operations Management, Strategic Planning"
    )


def test_normalize_competency_line_from_dict_and_repr():
    assert (
        normalize_competency_line(
            {"category": "Executive Leadership", "description": "COO, KPI, P&L"}
        )
        == "Executive Leadership: COO, KPI, P&L"
    )
    repr_line = "{'category': 'Tech Infrastructure', 'description': 'Odoo ERP, Agile'}"
    assert normalize_competency_line(repr_line) == "Tech Infrastructure: Odoo ERP, Agile"


def test_sanitize_competencies_filters_bad_lines():
    lines = [
        "UltaHost: UltaHost",
        "Executive Leadership: COO Leadership, Operations Management, KPI, P&L",
    ]
    out = sanitize_competencies(lines)
    assert len(out) == 1
    assert out[0].startswith("Executive Leadership:")


def test_merge_competencies_falls_back_to_baseline():
    baseline = ["Operations: Odoo ERP, KPI, P&L, process automation"]
    bad_llm = ["UltaHost: UltaHost", "Kraków: Kraków"]
    merged = merge_competencies(baseline, bad_llm, {"must_have_keywords": ["UltaHost"]})
    assert merged[0].startswith("Operations:")
    assert "UltaHost" not in merged[0] or "Odoo" in merged[0]


def test_parse_competencies_from_master_groups_skills(wizard_cv_text):
    comps = parse_competencies_from_master(wizard_cv_text)
    assert len(comps) >= 4
    assert any("Executive Leadership" in c for c in comps)
    assert all(":" in c for c in comps)


def test_resolve_experience_from_wizard_master(wizard_cv_text):
    settings = Settings()
    profile_md = Path("data/profile/01-candidate-profile.md").read_text(encoding="utf-8")
    entries = resolve_experience_entries(profile_md, settings)
    assert len(entries) >= 10
    coo = entries[0]
    assert coo.title == "Chief Operating Officer"
    assert coo.bullets
    assert "(uzupełnij)" not in coo.bullets[0]


def test_cv_draft_from_llm_dict_keeps_all_jobs_with_baseline_bullets():
    fallback = CvDraftData(
        profile_statement="Base",
        competencies=["Ops: Odoo"],
        experience_entries=[
            ExperienceEntry("08.2025-Present", "COO", "VentorTech", bullets=["A"]),
            ExperienceEntry("07.2025-Present", "Founder", "myOdoo", bullets=["B"]),
        ],
        education_entries=[],
    )
    data = {
        "experience_entries": [
            {"title": "COO", "company": "VentorTech", "bullets": ["Tailored A"]},
        ]
    }
    draft = cv_draft_from_llm_dict(data, fallback)
    assert len(draft.experience_entries) == 2
    assert draft.experience_entries[0].bullets == ["Tailored A"]
    assert draft.experience_entries[1].bullets == ["B"]


def test_select_experience_for_pdf_prioritizes_emphasis():
    entries = [
        ExperienceEntry("2025", "Founder", "Co", bullets=["x"]),
        ExperienceEntry("2025", "COO", "VentorTech", bullets=["y"]),
        ExperienceEntry("2020", "Manager", "Co2", bullets=["z"]),
    ]
    picked = select_experience_for_pdf(entries, ["Chief Operating Officer"], max_entries=2)
    assert picked[0].title == "COO"


def test_select_experience_for_pdf_reverse_chronological_after_emphasis():
    """Emphasis picks older commercial roles but output must be newest-first."""
    entries = [
        ExperienceEntry("07.2025-obecnie", "Founder", "myOdoo", bullets=["a"]),
        ExperienceEntry("06.2012-02.2014", "Commercial Advisor", "Enetel", bullets=["b"]),
        ExperienceEntry("11.2004-10.2005", "Commercial Advisor", "T1", bullets=["c"]),
        ExperienceEntry("08.2025-obecnie", "COO", "VentorTech", bullets=["d"]),
        ExperienceEntry("01.2023-08.2025", "Founding Board", "myOdoo", bullets=["e"]),
        ExperienceEntry("04.2018-01.2023", "Manager BD", "myOdoo", bullets=["f"]),
    ]
    picked = select_experience_for_pdf(
        entries, ["founder / co", "commercial advisor"], max_entries=6
    )
    periods = [e.period for e in picked]
    assert periods[0].startswith("08.2025") or periods[0].startswith("07.2025")
    assert "2004" not in periods[0] and "2012" not in periods[0]
    keys = [_period_end_key(p) for p in periods]
    assert keys == sorted(keys, reverse=True)


def test_build_cv_tex_has_summary_and_competencies_sections(wizard_cv_text):
    settings = Settings()
    draft = baseline_cv_draft(
        role="Chief Operating Officer ( COO )",
        company="UltaHost",
        profile_md=Path("data/profile/01-candidate-profile.md").read_text(encoding="utf-8"),
        language="en",
        settings=settings,
    )
    draft.emphasis_jobs = ["Chief Operating Officer", "Founder / Co-Owner"]
    identity = parse_identity(Path("data/profile/01-candidate-profile.md").read_text(encoding="utf-8"))
    tex = build_cv_tex(draft, identity, "ultahost")
    assert "Professional Summary" in tex
    assert "Skills \\& Competencies" in tex
    assert "Certifications" in tex
    assert "UltaHost: UltaHost" not in tex
    assert len(draft.competencies) >= 4
    assert "\\documentclass[10.5pt,a4paper]{extarticle}" in tex
    assert "\\cvheader{" in tex
    assert "cvNavy" in tex
    assert "\\cvskillcategory{" in tex
    assert "\\cvjob{" in tex
    assert "\\moderncv" not in tex
    assert "\\makecvtitle" not in tex
    assert "\\linespread" not in tex
    assert "\\cvBodyLeading" in tex
    assert "needspace" not in tex


def test_trim_cv_for_page_limit_removes_last_cvjob():
    from app.services.latex_service import LatexService

    tex = r"""
\cvsection{Professional Experience}
\cvjob{COO}{VentorTech \textbar{} Szczecin \textbar{} 2025}{\begin{itemize}
  \item First
\end{itemize}}
\cvjob{Founder}{myOdoo \textbar{} Szczecin \textbar{} 2025}{\begin{itemize}
  \item Second
\end{itemize}}
\cvsection{Education}
"""
    svc = LatexService(Path("."))
    trimmed = svc.trim_cv_for_page_limit(tex, 1)
    assert "\\cvjob{COO}" in trimmed
    assert "\\cvjob{Founder}" not in trimmed
    assert "\\cvsection{Education}" in trimmed


def test_trim_cv_for_page_limit_tightens_geometry_on_second_attempt():
    from app.services.latex_service import LatexService

    tex = "\\usepackage[margin=12mm]{geometry}\n\\cvjob{A}{B}{\\begin{itemize}\n  \\item x\n\\end{itemize}}"
    svc = LatexService(Path("."))
    trimmed = svc.trim_cv_for_page_limit(tex, 2)
    assert "\\usepackage[margin=10mm]{geometry}" in trimmed


def test_resolve_master_cv_text_uses_wizard_when_no_file():
    text = resolve_master_cv_text(Settings())
    assert "DOŚWIADCZENIE ZAWODOWE" in text


def test_ensure_role_in_profile_statement():
    from app.services.cv.competencies import ensure_role_in_profile_statement

    profile = "Leader with transformation and AI deployment experience."
    out = ensure_role_in_profile_statement(profile, "Global Operations, Transformation Director")
    assert out == profile


def test_ensure_role_in_profile_statement_project_manager_no_project_prefix():
    from app.services.cv.competencies import ensure_role_in_profile_statement

    profile = (
        "Chief Operating Officer, Founder, AI Transformation Leader with 15+ years "
        "of experience in technology and operations."
    )
    out = ensure_role_in_profile_statement(profile, "Project & Program Manager")
    assert not out.startswith("Project.")
    assert profile in out or out == profile


def test_cventry_item_balanced_braces():
    from app.services.latex_utils import cventry_item

    body = "\\begin{itemize}\n    \\item Example bullet\n\\end{itemize}"
    block = cventry_item("08.2025 - Present", "COO", "VentorTech", "Szczecin", body)
    assert block.count("{") == block.count("}")
