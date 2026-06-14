"""Deterministic PM/Program Manager ATS enrichment (truth-guarded, no extra LLM)."""

from __future__ import annotations

import re
from datetime import date
from typing import List, Optional, Tuple

from app.models.apply import JobParsed
from app.services.cv.ats_scoring import _keyword_in_text, bullet_quality_ratio
from app.services.cv.competencies import _split_competency, role_headline_for_job
from app.services.cv.language import normalize_cv_language
from app.services.cv.truth_guard import SkillTruthIndex
from app.services.cv.types import CvDraftData, ExperienceEntry

_PM_METHODOLOGY_TERMS = (
    "agile",
    "scrum",
    "waterfall",
    "project lifecycle",
    "risk management",
    "change management",
    "stakeholder management",
    "stakeholder engagement",
    "project management",
    "project reporting",
    "project documentation",
)

_LANGUAGE_GAP_RE = re.compile(
    r"english|angielsk|b1\+?|b2\+?|language proficien|język ang|jezyk ang",
    re.I,
)

_RESULT_VERB_START = re.compile(
    r"^(Managed|Led|Delivered|Implemented|Coordinated|Built|Developed|Established|"
    r"Optimized|Drove|Ensured|Defined|Monitored|Oversaw|Co-led|Reported|Facilitated|"
    r"Executed|Planned|Closed|Communicated|Provided|Organized|Streamlined|Achieved|"
    r"Drove|Directed|Supported|Launched|Reduced|Increased|Improved|Designed)\b",
    re.I,
)

_POLISH_RESULT_VERB_START = re.compile(
    r"^(Zarządzałem|Zarządzałam|Koordynowałem|Koordynowałam|Wdrożyłem|Wdrożyłam|"
    r"Nadzorowałem|Nadzorowałam|Odpowiadałem|Odpowiadałam|Prowadziłem|Prowadziłam|"
    r"Zbudowałem|Zbudowałam|Optymalizowałem|Optymalizowałam|Zdefiniowałem|Zdefiniowałam|"
    r"Monitorowałem|Monitorowałam|Współtworzyłem|Współtworzyłam|Reprezentowałem|"
    r"Reprezentowałam|Organizowałem|Organizowałam|Zarządzanie|Koordynowanie|Nadzór)\b",
    re.I,
)

_PM_SKILLS_BASE = (
    "Project Lifecycle Management",
    "Stakeholder Management",
    "Risk Management",
    "Change Management",
    "Project Reporting",
    "Project Documentation",
    "Agile",
    "Scrum",
    "Waterfall",
)

COO_LIFECYCLE_BULLET = (
    "Managed project portfolio across the full project lifecycle including planning, "
    "execution, monitoring, risk management, stakeholder communication and project closure."
)

MYODOO_AGILE_BULLET = (
    "Coordinated cross-functional teams using Agile project management practices "
    "and project collaboration tools."
)

_PM_SKILLS_BASE_PL = (
    "Zarządzanie cyklem życia projektu",
    "Zarządzanie interesariuszami",
    "Zarządzanie ryzykiem",
    "Zarządzanie zmianą",
    "Raportowanie projektowe",
    "Dokumentacja projektowa",
    "Agile",
    "Scrum",
    "Waterfall",
)

COO_LIFECYCLE_BULLET_PL = (
    "Zarządzanie portfelem projektów w pełnym cyklu życia, obejmującym planowanie, "
    "realizację, monitoring, zarządzanie ryzykiem, komunikację z interesariuszami "
    "i zamknięcie projektu."
)

MYODOO_AGILE_BULLET_PL = (
    "Koordynowanie zespołów międzyfunkcyjnych z wykorzystaniem praktyk Agile "
    "oraz narzędzi współpracy projektowej."
)


def is_pm_role(role: str) -> bool:
    r = (role or "").lower()
    return ("project" in r and "manager" in r) or "program manager" in r or "program &" in r


def _dedupe_keywords(items: List[str], limit: int = 12) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        s = str(item or "").strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _terms_from_posting(job_text: str) -> List[str]:
    hay = (job_text or "").lower()
    found: List[str] = []
    for term in _PM_METHODOLOGY_TERMS:
        if term in hay:
            found.append(term.title() if term != "agile" else "Agile")
            if term == "scrum":
                found[-1] = "Scrum"
            if term == "waterfall":
                found[-1] = "Waterfall"
    if "jira" in hay:
        found.append("JIRA")
    if "confluence" in hay:
        found.append("Confluence")
    return found


def _posting_grounded_keywords(
    keywords: List[str],
    *,
    job: JobParsed,
    tools_explicit: List[str],
    posting_terms: List[str],
) -> List[str]:
    """Keep keywords that appear in the posting text or are explicit tools."""
    hay = (job.raw_text or "").lower()
    tools = {str(t).lower() for t in tools_explicit if t}
    grounded: List[str] = []
    for item in keywords:
        s = str(item or "").strip()
        if not s:
            continue
        low = s.lower()
        if low in hay or any(part in hay for part in low.split() if len(part) >= 4):
            grounded.append(s)
        elif low in tools or any(t in low for t in tools):
            grounded.append(s)
    for term in posting_terms:
        if term not in grounded:
            grounded.append(term)
    for tool in tools_explicit:
        if tool and tool not in grounded:
            grounded.append(str(tool))
    return _dedupe_keywords(grounded, limit=10)


def normalize_job_targets(
    targets: dict,
    *,
    job: JobParsed,
    truth: SkillTruthIndex,
    profile_md: str = "",
) -> dict:
    """Post-process LLM job_targets for PM roles."""
    out = dict(targets or {})
    posting_terms = _terms_from_posting(job.raw_text)
    tools = [str(x) for x in (out.get("tools_explicit") or []) if x]

    must = list(out.get("must_have_keywords") or [])
    must.extend(tools)
    must.extend(posting_terms)
    must = _posting_grounded_keywords(
        must, job=job, tools_explicit=tools, posting_terms=posting_terms
    )
    out["must_have_keywords"] = _dedupe_keywords(
        truth.filter_keywords(must) or must,
        limit=10,
    )

    cleaned_norm: list = []
    profile_hay = (profile_md or "").lower()
    for norm in out.get("normalized_skills") or []:
        if not isinstance(norm, dict):
            continue
        cand = str(norm.get("candidate_term") or "").strip()
        post = str(norm.get("posting_term") or "").strip()
        if not post:
            continue
        if cand and cand.lower() in profile_hay:
            cleaned_norm.append(norm)
        elif truth.is_allowed(post) or truth.is_allowed(cand):
            cleaned_norm.append(norm)
    out["normalized_skills"] = cleaned_norm[:6]

    hints = out.get("keyword_placement_hints")
    if not isinstance(hints, dict):
        hints = {}
    summary_hints = [
        k
        for k in (out.get("must_have_keywords") or [])[:6]
        if k and not _LANGUAGE_GAP_RE.search(str(k))
    ]
    tools = [str(t) for t in (out.get("tools_explicit") or []) if t]
    summary_hints = _dedupe_keywords(summary_hints + tools, limit=5)
    hints["summary"] = summary_hints
    hints["top_bullets"] = _dedupe_keywords(
        list(hints.get("top_bullets") or []) + (out.get("must_have_keywords") or [])[:3],
        limit=5,
    )
    out["keyword_placement_hints"] = hints

    if is_pm_role(job.role):
        emphasis = list(out.get("emphasis_jobs") or [])
        for title in ("Chief Operating Officer", "Founder", "myOdoo"):
            if title not in emphasis:
                emphasis.append(title)
        out["emphasis_jobs"] = emphasis[:4]

    return out


def years_experience_from_profile(profile_md: str) -> Optional[int]:
    """Years since earliest ### job header year in profile."""
    years: List[int] = []
    for m in re.finditer(r"\((\d{2})\.(\d{4})\s*[-–]", profile_md or ""):
        years.append(int(m.group(2)))
    for m in re.finditer(r"\b(20\d{2})\b", profile_md or ""):
        y = int(m.group(1))
        if 1995 <= y <= date.today().year:
            years.append(y)
    if not years:
        return None
    earliest = min(years)
    delta = date.today().year - earliest
    return delta if delta >= 1 else None


def _years_phrase(profile_md: str, *, language: str = "en") -> str:
    n = years_experience_from_profile(profile_md)
    if normalize_cv_language(language) == "pl":
        if n is not None and n >= 3:
            return f"{n}+ lat doświadczenia"
        return "bogatym doświadczeniem"
    if n is not None and n >= 3:
        return f"{n}+ years of experience"
    return "extensive experience"


def _missing_lead_keywords(summary: str, job_targets: dict, min_count: int = 2) -> List[str]:
    must = [str(k) for k in (job_targets.get("must_have_keywords") or [])[:8] if k]
    hay = (summary or "").lower()
    hits = sum(1 for k in must if _keyword_in_text(k, hay))
    missing = [k for k in must if not _keyword_in_text(k, hay)]
    need = max(0, min_count - hits)
    return missing[:need]


def _lead_keyword_phrases(job_targets: dict, *, limit: int = 4) -> List[str]:
    """Exact must-have phrases to weave into the summary lead (verification substring match)."""
    must = [str(k) for k in (job_targets.get("must_have_keywords") or []) if k]
    preferred: List[str] = []
    for phrase in must:
        low = phrase.lower()
        if _LANGUAGE_GAP_RE.search(low):
            continue
        if low in (
            "agile",
            "scrum",
            "waterfall",
            "leadership",
            "communication skills",
            "problem-solving",
        ):
            continue
        preferred.append(phrase)
    if not preferred:
        preferred = [k for k in must if not _LANGUAGE_GAP_RE.search(k.lower())][:limit]
    return _dedupe_keywords(preferred, limit=limit)


def enrich_summary_for_pm(
    summary: str,
    role: str,
    job_targets: dict,
    profile_md: str,
    truth: SkillTruthIndex,
    *,
    min_lead_keywords: int = 2,
    language: str = "en",
) -> str:
    lang = normalize_cv_language(language)
    headline = role_headline_for_job(role)
    years = _years_phrase(profile_md, language=lang)
    lead_kw = _lead_keyword_phrases(job_targets, limit=max(min_lead_keywords + 2, 4))
    kw_clause = ", ".join(lead_kw[:4]) if lead_kw else (
        "cykl życia projektu, zarządzanie interesariuszami"
        if lang == "pl"
        else "project lifecycle, stakeholder engagement"
    )
    if lang == "pl":
        body = (
            f"{headline} z {years} w zakresie {kw_clause}. "
            f"Doświadczenie w zarządzaniu projektami wdrożeniowymi ERP oraz zespołami "
            f"międzyfunkcyjnymi w pełnym cyklu życia projektu, obejmującym planowanie, "
            f"realizację, monitoring, zarządzanie ryzykiem i komunikację z interesariuszami. "
            f"Udokumentowane wyniki w prowadzeniu organizacji delivery oraz koordynacji "
            f"interesariuszy biznesowych, technicznych i zewnętrznych."
        )
        missing = _missing_lead_keywords(body[:600], job_targets, min_count=min_lead_keywords)
        if missing:
            body = body.rstrip(".") + ". Kluczowe obszary: " + ", ".join(missing[:3]) + "."
    else:
        body = (
            f"{headline} with {years} in {kw_clause}. "
            f"Experienced managing ERP implementation projects and cross-functional teams across "
            f"the full project lifecycle, including planning, execution, monitoring, risk management, "
            f"and stakeholder communication. "
            f"Proven track record leading delivery organizations and coordinating business, "
            f"technical and external stakeholders."
        )
        missing = _missing_lead_keywords(body[:600], job_targets, min_count=min_lead_keywords)
        if missing:
            body = body.rstrip(".") + ". Core strengths include " + ", ".join(missing[:3]) + "."

    sanitized, _ = truth.sanitize_text(body.strip())
    return sanitized


def _jira_confluence_line(
    job_targets: dict,
    truth: SkillTruthIndex,
    *,
    language: str = "en",
) -> Optional[str]:
    tools = [str(t).lower() for t in (job_targets.get("tools_explicit") or [])]
    has_jira = any("jira" in t for t in tools) or truth.is_allowed("jira")
    has_conf = any("confluence" in t for t in tools) or truth.is_allowed("confluence")
    if normalize_cv_language(language) == "pl":
        if has_jira and has_conf:
            return "Jira / Confluence (lub podobne platformy zarządzania projektami)"
        if has_jira:
            return "Jira (lub podobne platformy zarządzania projektami)"
        if has_conf:
            return "Confluence (lub podobne platformy zarządzania projektami)"
        return None
    if has_jira and has_conf:
        return "Jira / Confluence (or similar project management platforms)"
    if has_jira:
        return "Jira (or similar project management platforms)"
    if has_conf:
        return "Confluence (or similar project management platforms)"
    return None


def enrich_pm_competencies(
    competencies: List[str],
    job_targets: dict,
    truth: SkillTruthIndex,
    *,
    max_lines: int = 7,
    language: str = "en",
) -> List[str]:
    lang = normalize_cv_language(language)
    lines = list(competencies or [])
    base_skills = _PM_SKILLS_BASE_PL if lang == "pl" else _PM_SKILLS_BASE
    pm_skills = [s for s in base_skills if truth.is_allowed(s) or len(s) > 12]
    jira_line = _jira_confluence_line(job_targets, truth, language=lang)
    if jira_line:
        pm_skills.append(jira_line)

    pm_category = (
        "Zarządzanie projektami i programami"
        if lang == "pl"
        else "Project & Program Management"
    )
    existing_idx = None
    for i, line in enumerate(lines):
        label, _ = _split_competency(line)
        if label.lower().startswith("project") and "program" in label.lower():
            existing_idx = i
            break

    pm_detail = ", ".join(_dedupe_keywords(pm_skills, limit=12))
    pm_line = f"{pm_category}: {pm_detail}"

    if existing_idx is not None:
        label, detail = _split_competency(lines[existing_idx])
        parts = [p.strip() for p in detail.split(",") if p.strip()]
        merged = _dedupe_keywords(parts + pm_skills, limit=14)
        lines[existing_idx] = f"{label}: {', '.join(merged)}"
    else:
        lines.insert(min(1, len(lines)), pm_line)

    return lines[:max_lines]


def _normalize_bullet(bullet: str, truth: SkillTruthIndex, *, language: str = "en") -> str:
    b = re.sub(r"^[-•*]\s+", "", (bullet or "").strip())
    if not b:
        return b
    lang = normalize_cv_language(language)
    if lang == "pl":
        if not _POLISH_RESULT_VERB_START.match(b) and not _RESULT_VERB_START.match(b):
            if b[0].islower():
                b = b[0].upper() + b[1:]
    elif not _RESULT_VERB_START.match(b):
        b = f"Managed {b[0].lower() + b[1:]}" if len(b) > 1 else f"Managed {b}"
    clean, _ = truth.sanitize_text(b)
    return clean


def _match_entry(title: str, company: str, *patterns: str) -> bool:
    t = (title or "").lower()
    c = (company or "").lower()
    blob = f"{t} {c}"
    return any(p.lower() in blob for p in patterns)


def enrich_pm_experience_bullets(
    entries: List[ExperienceEntry],
    job_targets: dict,
    truth: SkillTruthIndex,
    *,
    language: str = "en",
) -> List[ExperienceEntry]:
    lang = normalize_cv_language(language)
    lifecycle_tpl = COO_LIFECYCLE_BULLET_PL if lang == "pl" else COO_LIFECYCLE_BULLET
    agile_tpl = MYODOO_AGILE_BULLET_PL if lang == "pl" else MYODOO_AGILE_BULLET
    lifecycle_markers = (
        ("cyklu życia projektu", "pełnym cyklu")
        if lang == "pl"
        else ("project lifecycle",)
    )
    out: List[ExperienceEntry] = []
    for entry in entries:
        bullets = [
            _normalize_bullet(b, truth, language=lang) for b in (entry.bullets or []) if b
        ]

        if _match_entry(entry.title, entry.company, "chief operating", "coo", "ventortech"):
            lifecycle = _normalize_bullet(lifecycle_tpl, truth, language=lang)
            if not any(any(m in b.lower() for m in lifecycle_markers) for b in bullets):
                bullets = [lifecycle] + bullets[:4]

        if _match_entry(entry.title, entry.company, "founder", "co-owner", "myodoo"):
            agile_b = _normalize_bullet(agile_tpl, truth, language=lang)
            if not any("agile" in b.lower() for b in bullets):
                bullets = [agile_b] + bullets[:3]

        bullets = [_normalize_bullet(b, truth, language=lang) for b in bullets if b]
        out.append(
            ExperienceEntry(
                period=entry.period,
                title=entry.title,
                company=entry.company,
                location=entry.location,
                bullets=bullets[:5],
            )
        )
    return out


def enrich_tools_in_skills(
    competencies: List[str],
    job_targets: dict,
    truth: SkillTruthIndex,
    *,
    language: str = "en",
    max_lines: int = 7,
) -> List[str]:
    """Inject JIRA/Confluence into skills for non-PM roles when posting requires them."""
    jira_line = _jira_confluence_line(job_targets, truth, language=language)
    if not jira_line:
        return competencies
    blob = " ".join(competencies or []).lower()
    if "jira" in blob and "confluence" in blob:
        return competencies
    lang = normalize_cv_language(language)
    tools_category = "Narzędzia projektowe" if lang == "pl" else "Project Tools"
    lines = list(competencies or [])
    for i, line in enumerate(lines):
        label, _ = _split_competency(line)
        if label.lower().startswith("project tool") or "narzędzi" in label.lower():
            label, detail = _split_competency(line)
            parts = [p.strip() for p in detail.split(",") if p.strip()]
            merged = _dedupe_keywords(parts + [jira_line], limit=10)
            lines[i] = f"{label}: {', '.join(merged)}"
            return lines[:max_lines]
    lines.insert(min(2, len(lines)), f"{tools_category}: {jira_line}")
    return lines[:max_lines]


def enrich_summary_lead_keywords(
    summary: str,
    job_targets: dict,
    *,
    language: str = "en",
    min_count: int = 2,
) -> str:
    """Weave missing must-have phrases into the summary opening (verification substring match)."""
    lang = normalize_cv_language(language)
    must = [str(k) for k in (job_targets.get("must_have_keywords") or [])[:8] if k]
    lead = (summary or "").strip()
    if not must or not lead:
        return summary

    hay_lead = lead[:400].lower()
    hits = sum(1 for k in must if _keyword_in_text(k, hay_lead))
    if hits >= min_count:
        return summary

    missing = [k for k in must if not _keyword_in_text(k, hay_lead)]
    need = max(min_count - hits, 1)
    to_weave = missing[: max(need, 2)]
    kw_clause = ", ".join(to_weave[:3])

    if lang == "pl":
        woven = f"Doświadczenie w zakresie {kw_clause}. {lead}"
    else:
        woven = f"Experienced in {kw_clause}. {lead}"

    final_hay = woven[:600].lower()
    if sum(1 for k in must if _keyword_in_text(k, final_hay)) < min_count:
        extra = [k for k in missing if not _keyword_in_text(k, final_hay)][:2]
        if extra:
            clause = ", ".join(extra)
            if lang == "pl":
                woven = woven.rstrip(". ") + f". Kluczowe obszary: {clause}."
            else:
                woven = woven.rstrip(". ") + f". Core focus: {clause}."
    return woven


def apply_pm_ats_enrichment(
    *,
    profile_statement: str,
    competencies: List[str],
    experience_entries: List[ExperienceEntry],
    job: JobParsed,
    profile_md: str,
    job_targets: dict,
    truth: SkillTruthIndex,
    enabled: bool = True,
    min_lead_keywords: int = 2,
) -> Tuple[str, List[str], List[ExperienceEntry], List[str]]:
    """Return enriched profile, competencies, experience, and decision notes."""
    notes: List[str] = []
    if not enabled:
        return profile_statement, competencies, experience_entries, notes

    cv_lang = normalize_cv_language(job.language)
    new_summary = profile_statement
    new_comp = list(competencies)
    new_exp = list(experience_entries)

    if is_pm_role(job.role):
        new_summary = enrich_summary_for_pm(
            profile_statement,
            job.role,
            job_targets,
            profile_md,
            truth,
            min_lead_keywords=min_lead_keywords,
            language=cv_lang,
        )
        if new_summary != profile_statement:
            notes.append("ATS enrichment: PM summary with lifecycle/stakeholder keywords")

        new_comp = enrich_pm_competencies(
            competencies, job_targets, truth, language=cv_lang
        )
        if new_comp != competencies:
            notes.append("ATS enrichment: Project & Program Management skills category")

        new_exp = enrich_pm_experience_bullets(
            experience_entries, job_targets, truth, language=cv_lang
        )
        if new_exp != experience_entries:
            notes.append("ATS enrichment: COO lifecycle + myOdoo Agile bullets")
    else:
        enriched = enrich_summary_lead_keywords(
            profile_statement,
            job_targets,
            language=cv_lang,
            min_count=min_lead_keywords,
        )
        if enriched != profile_statement:
            new_summary = enriched
            notes.append("ATS enrichment: summary lead keywords")

        new_comp = enrich_tools_in_skills(
            new_comp, job_targets, truth, language=cv_lang
        )
        if new_comp != competencies:
            notes.append("ATS enrichment: JIRA/Confluence in skills")

    bullets = [b for e in new_exp for b in e.bullets]
    if bullets:
        bq = bullet_quality_ratio(bullets)
        notes.append(f"ATS enrichment: bullet quality {bq:.0%}")

    return new_summary, new_comp, new_exp, notes
