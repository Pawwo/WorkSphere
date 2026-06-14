"""CV draft building."""
from __future__ import annotations

import re
from typing import List, Optional

from app.config import Settings, get_settings
from app.services.cv.competencies import (
    parse_competencies_from_master,
    role_headline_for_job,
)
from app.services.cv.experience import (
    _is_placeholder_bullet,
    _norm_exp_key,
    resolve_experience_entries,
)
from app.services.cv.identity import (
    default_competencies_from_profile,
    parse_certifications_from_profile,
    parse_education_from_profile,
    parse_identity,
)
from app.services.cv.language import (
    apply_static_cv_language,
    languages_line_from_profile,
    normalize_cv_language,
    references_line_for,
)
from app.services.inbox.language_levels import load_candidate_languages
from app.services.cv.master import load_master_ats_summary, resolve_master_cv_text
from app.services.cv.types import CvDraftData, EducationEntry, ExperienceEntry

CV_MAX_ENTRIES_ON_PDF = 6


def baseline_cv_draft(
    *,
    role: str,
    company: str,
    profile_md: str,
    job_posting: str = "",
    language: str = "en",
    settings: Optional[Settings] = None,
) -> CvDraftData:
    """Profile + master ATS summary — factual base before LLM tailoring in CvTailorService."""
    settings = settings or get_settings()
    cv_lang = normalize_cv_language(language)
    master_text = resolve_master_cv_text(settings)
    ats = load_master_ats_summary(settings, language=cv_lang)
    experience = resolve_experience_entries(profile_md, settings)
    education = parse_education_from_profile(profile_md)
    identity = parse_identity(profile_md)

    competencies = parse_competencies_from_master(master_text)
    if not competencies:
        competencies = default_competencies_from_profile(profile_md)

    profile_statement = ats.split("\n\n")[0].strip() if ats else ""
    if len(profile_statement) > 700:
        profile_statement = profile_statement[:697] + "..."

    pubs: List[str] = []
    awards: List[str] = []
    in_pub = in_aw = False
    for line in profile_md.splitlines():
        if line.strip() == "## Publications":
            in_pub, in_aw = True, False
            continue
        if line.strip() == "## Awards":
            in_aw, in_pub = True, False
            continue
        if line.startswith("## ") and in_pub:
            in_pub = False
        if line.startswith("## ") and in_aw:
            in_aw = False
        if in_pub and re.match(r"^\d+\.", line.strip()):
            pubs.append(re.sub(r"^\d+\.\s*", "", line.strip()))
        if in_aw and line.strip().startswith("- "):
            awards.append(line.strip()[2:])

    profile_langs = load_candidate_languages(settings)
    draft = CvDraftData(
        profile_statement=profile_statement,
        competencies=competencies,
        experience_entries=experience,
        education_entries=education,
        languages_line=languages_line_from_profile(profile_langs, cv_lang),
        publications=pubs[:3],
        awards=awards[:3],
        certifications=parse_certifications_from_profile(profile_md)[:6],
        role_headline=role_headline_for_job(role),
        cv_language=cv_lang,
        references_line=references_line_for(cv_lang),
    )
    return apply_static_cv_language(draft, cv_lang, profile_md=profile_md)


def _valid_period(period: str) -> bool:
    p = (period or "").strip()
    if not p or len(p) > 35:
        return False
    if p.count("(") > 1 or p.startswith("("):
        return False
    return bool(re.search(r"\d{2}\.\d{4}", p))


def cv_draft_from_llm_dict(data: dict, fallback: CvDraftData) -> CvDraftData:
    """Merge LLM JSON into baseline; preserve baseline job order."""
    llm_by_key: dict[str, dict] = {}
    for e in data.get("experience_entries") or []:
        if isinstance(e, dict) and e.get("title"):
            llm_by_key[_norm_exp_key(str(e.get("title", "")), str(e.get("company", "")))] = e

    exp: List[ExperienceEntry] = []
    for fb in fallback.experience_entries:
        key = _norm_exp_key(fb.title, fb.company)
        le = llm_by_key.get(key)
        bullets = [b for b in fb.bullets if not _is_placeholder_bullet(b)]
        period, title, company, location = fb.period, fb.title, fb.company, fb.location
        if le:
            llm_bullets = [
                str(b) for b in (le.get("bullets") or []) if not _is_placeholder_bullet(str(b))
            ]
            if llm_bullets:
                bullets = llm_bullets
            period = str(le.get("period") or period)
            if not _valid_period(period):
                period = fb.period
            title = str(le.get("title") or title)
            company = str(le.get("company") or company)
            location = str(le.get("location") or location)
        if not bullets:
            continue
        exp.append(
            ExperienceEntry(
                period=period,
                title=title,
                company=company,
                location=location,
                bullets=bullets,
            )
        )

    if not exp:
        exp = [
            e
            for e in fallback.experience_entries
            if e.bullets and not all(_is_placeholder_bullet(b) for b in e.bullets)
        ]

    edu: List[EducationEntry] = []
    for e in data.get("education_entries") or []:
        if isinstance(e, dict):
            edu.append(
                EducationEntry(
                    period=str(e.get("period", "")),
                    degree=str(e.get("degree", "")),
                    institution=str(e.get("institution", "")),
                    location=str(e.get("location", "")),
                    detail=str(e.get("detail", "")),
                )
            )
    elif_line = data.get("education_line")
    if not edu and elif_line:
        edu = fallback.education_entries

    comps = data.get("competencies")
    if comps:
        competencies = [str(c) for c in comps]
    else:
        competencies = list(fallback.competencies)

    return CvDraftData(
        profile_statement=str(data.get("profile_statement") or fallback.profile_statement),
        competencies=competencies,
        experience_entries=exp or fallback.experience_entries,
        education_entries=edu or fallback.education_entries,
        languages_line=str(data.get("languages_line") or fallback.languages_line),
        publications=[str(p) for p in (data.get("publications") or fallback.publications)][:3],
        awards=[str(a) for a in (data.get("awards") or fallback.awards)][:3],
        certifications=[
            str(c) for c in (data.get("certifications") or fallback.certifications)
        ][:6],
        role_headline=str(data.get("role_headline") or fallback.role_headline),
        emphasis_jobs=list(data.get("emphasis_jobs") or fallback.emphasis_jobs),
        cv_language=str(data.get("cv_language") or fallback.cv_language),
        references_line=str(data.get("references_line") or fallback.references_line),
    )
