"""HTML CV document builder (reference design)."""

from __future__ import annotations

import re
from typing import List, Optional

from markupsafe import Markup, escape

from app.services.cv.draft import CV_MAX_ENTRIES_ON_PDF
from app.services.cv.experience import _is_placeholder_bullet, select_experience_for_pdf
from app.services.cv.language import apply_static_cv_language, localize_identity
from app.services.cv.template_env import get_cv_template_env, load_cv_css
from app.services.cv.ats_scoring import collect_highlight_keywords, highlight_keywords_in_text
from app.services.cv.types import CvDraftData

_DEFAULT_REFERENCES = frozenset(
    {
        "available upon request.",
        "available upon request",
        "na życzenie.",
        "na życzenie",
    }
)

_SECTION_LABELS_EN = {
    "summary": "Professional Summary",
    "skills": "Skills & Competencies",
    "experience": "Professional Experience",
    "education": "Education",
    "certifications": "Certifications & Training",
    "publications": "Publications",
    "awards": "Honors and Awards",
    "languages": "Languages",
    "references": "References",
}

_SECTION_LABELS_PL = {
    "summary": "Podsumowanie zawodowe",
    "skills": "Umiejętności i kompetencje",
    "experience": "Doświadczenie zawodowe",
    "education": "Wykształcenie",
    "certifications": "Certyfikaty i szkolenia",
    "publications": "Publikacje",
    "awards": "Wyróżnienia",
    "languages": "Języki",
    "references": "Referencje",
}


def format_contact_html(identity: dict) -> Markup:
    """Build header contact line with optional LinkedIn link."""
    parts: List[Markup] = []
    for key in ("location", "phone", "email"):
        value = (identity.get(key) or "").strip()
        if value and value not in ("—", "-"):
            parts.append(Markup(escape(value)))
    linkedin = (identity.get("linkedin") or "").strip()
    if linkedin and linkedin not in ("—", "-"):
        safe_url = escape(linkedin)
        parts.append(Markup(f'<a href="{safe_url}">LinkedIn</a>'))
    return Markup(" | ".join(str(p) for p in parts))


def _format_job_meta(company: str, location: str, period: str) -> str:
    meta_parts = [p for p in (company, location, period) if p and p.strip()]
    return " | ".join(meta_parts)


def _should_show_references(references_line: str) -> bool:
    line = (references_line or "").strip()
    if not line:
        return False
    return line.lower() not in _DEFAULT_REFERENCES


def _split_competency(line: str) -> tuple[str, str]:
    from app.services.cv.competencies import normalize_competency_line

    normalized = normalize_competency_line(line)
    if ":" in normalized:
        category, items = normalized.split(":", 1)
        return category.strip(), items.strip()
    return normalized.strip(), ""


def _clean_bullet_text(text: object) -> str:
    raw = str(text) if text is not None else ""
    return re.sub(r"^[-•*]\s+", "", raw.strip())


def _section_labels(lang: str) -> dict:
    if (lang or "").lower().startswith("pl"):
        return dict(_SECTION_LABELS_PL)
    return dict(_SECTION_LABELS_EN)


def _format_period_display(period: str, *, lang: str) -> str:
    """Normalize date line for ATS (MM/YYYY style where possible)."""
    p = (period or "").strip()
    if not p:
        return p
    p = p.replace("–", "–").replace("--", "–")
    p = re.sub(r"\bPresent\b", "obecnie" if lang == "pl" else "Present", p, flags=re.I)
    p = re.sub(r"\bobecnie\b", "obecnie" if lang == "pl" else "Present", p, flags=re.I)
    return p


def build_cv_html(
    draft: CvDraftData,
    identity: dict,
    company_slug: str = "",
    *,
    profile_md: str = "",
    job_targets: dict | None = None,
    highlight_keywords: bool = True,
) -> str:
    """Render full CV HTML document from draft data."""
    del company_slug  # reserved for future per-company assets
    lang = draft.cv_language or "en"
    draft = apply_static_cv_language(draft, lang, profile_md=profile_md)
    identity = localize_identity(identity, draft.cv_language)
    lang = "pl" if (draft.cv_language or "").lower().startswith("pl") else "en"
    labels = _section_labels(draft.cv_language or lang)

    skills = []
    for comp in draft.competencies[:7]:
        category, items = _split_competency(comp)
        if category:
            skills.append({"category": category, "detail": items or category})

    selected = select_experience_for_pdf(
        draft.experience_entries,
        draft.emphasis_jobs,
        max_entries=CV_MAX_ENTRIES_ON_PDF,
    )
    kw_highlight: List[str] = []
    if highlight_keywords and job_targets:
        kw_highlight = collect_highlight_keywords(job_targets)

    jobs = []
    for i, entry in enumerate(selected):
        clean_bullets = [
            _clean_bullet_text(b) for b in entry.bullets if not _is_placeholder_bullet(b)
        ]
        if i == 0:
            limit = 4
        elif i < 3:
            limit = 3
        else:
            limit = 2
        bullets = clean_bullets[:limit]
        if not bullets:
            continue
        rendered_bullets = bullets
        if kw_highlight:
            rendered_bullets = [
                highlight_keywords_in_text(b, kw_highlight) for b in bullets
            ]
        period = _format_period_display(entry.period, lang=lang)
        jobs.append(
            {
                "title": entry.title,
                "meta": _format_job_meta(entry.company, entry.location, period),
                "bullets": rendered_bullets,
            }
        )

    education = []
    for ed in draft.education_entries[:3]:
        meta_parts = [p for p in (ed.institution, ed.location, ed.period) if p and p.strip()]
        education.append(
            {
                "degree": ed.degree,
                "detail": ed.detail or "",
                "meta": " | ".join(meta_parts),
            }
        )

    certifications = list(draft.certifications[:6])
    publications = list(draft.publications[:3])
    awards = list(draft.awards[:3])
    references_line = draft.references_line if _should_show_references(draft.references_line) else ""

    template = get_cv_template_env().get_template("cv.html.jinja2")
    return template.render(
        lang=lang,
        css=load_cv_css("cv.css"),
        identity={"name": identity.get("name", "")},
        headline=draft.role_headline or "",
        contact_html=format_contact_html(identity),
        profile_statement=draft.profile_statement,
        labels=labels,
        skills=skills,
        jobs=jobs,
        education=education,
        certifications=certifications,
        publications=publications,
        awards=awards,
        languages_line=draft.languages_line or "",
        references_line=references_line,
    )


def build_cover_html(
    cover_data: dict,
    identity: dict,
    company_slug: str = "",
    role_slug: str = "",
) -> str:
    """Render cover letter HTML document."""
    del company_slug, role_slug
    template = get_cv_template_env().get_template("cover.html.jinja2")
    return template.render(
        lang="en",
        css=load_cv_css("cover.css"),
        identity={"name": identity.get("name", "")},
        contact_html=format_contact_html(identity),
        salutation=cover_data.get("salutation", ""),
        opening=cover_data.get("opening", ""),
        body=cover_data.get("body", ""),
        bullets=[b for b in cover_data.get("bullets", []) if b],
        motivation=cover_data.get("motivation", ""),
        closing=cover_data.get("closing", ""),
    )
