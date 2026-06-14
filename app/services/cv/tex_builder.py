"""LaTeX CV document builder."""
from __future__ import annotations

from typing import List

from app.services.cv.draft import CV_MAX_ENTRIES_ON_PDF
from app.services.cv.experience import _is_placeholder_bullet, select_experience_for_pdf
from app.services.cv.language import localize_identity
from app.services.cv.tex_style import cv_tex_preamble
from app.services.cv.types import CvDraftData
from app.services.latex_utils import escape_latex

_DEFAULT_REFERENCES = frozenset(
    {
        "available upon request.",
        "available upon request",
        "na życzenie.",
        "na życzenie",
    }
)


def format_contact_line(identity: dict) -> str:
    """Build header contact line: location | phone | email | linkedin."""
    parts: List[str] = []
    for key in ("location", "phone", "email"):
        value = (identity.get(key) or "").strip()
        if value and value not in ("—", "-"):
            parts.append(escape_latex(value))
    linkedin = (identity.get("linkedin") or "").strip()
    if linkedin and linkedin not in ("—", "-"):
        parts.append(f"\\href{{{escape_latex(linkedin)}}}{{LinkedIn}}")
    return " \\textbar{} ".join(parts)


def _format_job_meta(company: str, location: str, period: str) -> str:
    meta_parts = [p for p in (company, location, period) if p and p.strip()]
    return " \\textbar{} ".join(escape_latex(p) for p in meta_parts)


def _should_show_references(references_line: str) -> bool:
    line = (references_line or "").strip()
    if not line:
        return False
    return line.lower() not in _DEFAULT_REFERENCES


def build_cv_tex(draft: CvDraftData, identity: dict, company_slug: str = "") -> str:
    """Custom article CV template (HTML-inspired single-column layout)."""
    identity = localize_identity(identity, draft.cv_language)
    pdf_title = escape_latex(f"{identity['name']} - CV")
    headline = escape_latex(draft.role_headline or "")
    contact = format_contact_line(identity)

    skill_blocks = "\n".join(
        f"\\cvskillcategory{{{escape_latex(c.split(':', 1)[0])}}}"
        f"{{{escape_latex(c.split(':', 1)[1].strip() if ':' in c else c)}}}"
        for c in draft.competencies[:7]
    )

    selected = select_experience_for_pdf(
        draft.experience_entries,
        draft.emphasis_jobs,
        max_entries=CV_MAX_ENTRIES_ON_PDF,
    )

    exp_blocks: List[str] = []
    for i, e in enumerate(selected):
        clean_bullets = [b for b in e.bullets if not _is_placeholder_bullet(b)]
        if i == 0:
            limit = 4
        elif i < 3:
            limit = 3
        else:
            limit = 2
        bullets = "\n".join(f"  \\item {escape_latex(b)}" for b in clean_bullets[:limit])
        if not bullets:
            continue
        body = f"\\begin{{itemize}}\n{bullets}\n\\end{{itemize}}"
        meta = _format_job_meta(e.company, e.location, e.period)
        exp_blocks.append(f"\\cvjob{{{escape_latex(e.title)}}}{{{meta}}}{{{body}}}")
    experience_body = "\n".join(exp_blocks)

    edu_blocks: List[str] = []
    for ed in draft.education_entries[:3]:
        degree = f"\\textbf{{{escape_latex(ed.degree)}}}"
        if ed.detail:
            degree += f"\\\\\n{escape_latex(ed.detail)}"
        meta_parts = [p for p in (ed.institution, ed.location, ed.period) if p and p.strip()]
        meta = " \\textbar{} ".join(escape_latex(p) for p in meta_parts)
        edu_blocks.append(f"\\cveducation{{{degree}}}{{{meta}}}")
    education_body = "\n".join(edu_blocks)

    pubs = "\n".join(f"  \\item {escape_latex(p)}" for p in draft.publications[:3])
    awards = "\n".join(f"  \\item \\textbf{{{escape_latex(a)}}}" for a in draft.awards[:3])
    certs = "\n".join(f"  \\item {escape_latex(c)}" for c in draft.certifications[:6])

    pub_section = ""
    if pubs:
        pub_section = f"""
\\cvsection{{Publications}}
\\begin{{itemize}}
{pubs}
\\end{{itemize}}
"""

    awards_section = ""
    if awards:
        awards_section = f"""
\\cvsection{{Honors and Awards}}
\\begin{{itemize}}
{awards}
\\end{{itemize}}
"""

    cert_section = ""
    if certs:
        cert_section = f"""
\\cvsection{{Certifications \\& Training}}
\\begin{{itemize}}
{certs}
\\end{{itemize}}
"""

    refs_section = ""
    if _should_show_references(draft.references_line):
        refs_section = f"""
\\cvsection{{References}}
\\begin{{itemize}}
  \\item {escape_latex(draft.references_line)}
\\end{{itemize}}
"""

    return f"""{cv_tex_preamble(pdf_title)}
\\begin{{document}}

\\cvheader{{{escape_latex(identity['name'])}}}{{{headline}}}{{{contact}}}

\\cvsection{{Professional Summary}}
{escape_latex(draft.profile_statement)}

\\cvsection{{Skills \\& Competencies}}
{skill_blocks}

\\cvsection{{Professional Experience}}
{experience_body}

\\cvsection{{Education}}
{education_body}
{cert_section}
\\cvsection{{Languages}}
{escape_latex(draft.languages_line)}
{pub_section}{awards_section}{refs_section}
\\end{{document}}
"""
