"""Step 6 verification checklist from data/profile/CLAUDE.md."""

from __future__ import annotations

import re
from typing import List, Literal, Optional

from app.config import get_settings
from app.models.apply import FitEvaluation, JobParsed, ReviewerResult
from app.services.cv.ats_scoring import (
    _keyword_in_text,
    ats_keyword_coverage,
    bullet_quality_ratio,
    compute_ats_score,
    experience_bullets_from_html,
    html_to_plain_text,
    section_order_valid,
)
from app.services.apply_service import short_company_name
from app.services.cv.competencies import _role_keywords_present
from app.services.cv.truth_guard import build_skill_truth_index
from app.services.job_fetcher import _linkedin_body_usable

RendererFormat = Literal["latex", "html", "auto"]

_LINKEDIN_CHROME_TOKENS = frozenset(
    {
        "poziom",
        "hierarchii",
        "kadra",
        "średniego",
        "szczebla",
        "forma",
        "zatrudnienia",
        "pełny",
        "zaloguj",
        "hasła",
        "cookie",
        "prywatność",
        "linkedin",
        "polecenia",
        "referrals",
        "alert",
        "email",
        "phone",
        "password",
    }
)


def _is_llm_degraded(tailoring_decisions: Optional[List[str]]) -> bool:
    if not tailoring_decisions:
        return False
    blob = " ".join(tailoring_decisions).lower()
    return any(
        phrase in blob
        for phrase in (
            "llm fallback",
            "llm baseline",
            "llm niedostępny",
            "skipped 4 tailor",
            "skipped 3 tailor",
        )
    )


def _cover_mentions_company(job: JobParsed, cover_content: str) -> bool:
    cover_low = cover_content.lower()
    candidates = [
        job.company,
        short_company_name(job.company).replace("_", " "),
        job.company.split(" Sp.")[0].strip(),
    ]
    for candidate in candidates:
        c = (candidate or "").strip().lower()
        if len(c) >= 3 and c in cover_low:
            return True
    return False


def detect_renderer_format(
    cv_content: str,
    cover_content: str,
    renderer: RendererFormat = "auto",
) -> str:
    if renderer in ("latex", "html"):
        return renderer
    cv_head = cv_content.lstrip()[:400].lower()
    if cv_head.startswith("<!doctype") or "<html" in cv_head:
        return "html"
    if "\\documentclass" in cv_content:
        return "latex"
    cover_head = cover_content.lstrip()[:400].lower()
    if cover_head.startswith("<!doctype") or "<html" in cover_head:
        return "html"
    if "\\documentclass" in cover_content:
        return "latex"
    return "latex"


def run_verification_checklist(
    *,
    job: JobParsed,
    cv_tex: str,
    cover_tex: str,
    profile_md: str,
    evaluation: FitEvaluation,
    reviewer: ReviewerResult,
    pdf_files: List[str],
    pdf_checks: List[str],
    renderer: RendererFormat = "auto",
    job_targets: Optional[dict] = None,
    tailoring_decisions: Optional[List[str]] = None,
) -> dict:
    fmt = detect_renderer_format(cv_tex, cover_tex, renderer)
    degraded = _is_llm_degraded(tailoring_decisions)
    if fmt == "html":
        return _run_html_checklist(
            job=job,
            cv_html=cv_tex,
            cover_html=cover_tex,
            profile_md=profile_md,
            evaluation=evaluation,
            reviewer=reviewer,
            pdf_files=pdf_files,
            pdf_checks=pdf_checks,
            job_targets=job_targets or {},
            llm_degraded=degraded,
        )
    return _run_latex_checklist(
        job=job,
        cv_tex=cv_tex,
        cover_tex=cover_tex,
        profile_md=profile_md,
        evaluation=evaluation,
        reviewer=reviewer,
        pdf_files=pdf_files,
        pdf_checks=pdf_checks,
        job_targets=job_targets or {},
        tailoring_decisions=tailoring_decisions,
    )


def _run_latex_checklist(
    *,
    job: JobParsed,
    cv_tex: str,
    cover_tex: str,
    profile_md: str,
    evaluation: FitEvaluation,
    reviewer: ReviewerResult,
    pdf_files: List[str],
    pdf_checks: List[str],
    job_targets: Optional[dict] = None,
    tailoring_decisions: Optional[List[str]] = None,
) -> dict:
    items: List[dict] = []

    def add(category: str, label: str, passed: bool, note: str = "") -> None:
        items.append({"category": category, "label": label, "pass": passed, "note": note})

    _add_shared_factual_targeting(
        add,
        job,
        cv_tex,
        cover_tex,
        evaluation,
        profile_md,
        fmt="latex",
        job_targets=job_targets or {},
    )
    add(
        "consistency",
        "CV uses article template",
        "\\documentclass[10.5pt,a4paper]{extarticle}" in cv_tex and "\\cvheader{" in cv_tex,
        "",
    )
    add("consistency", "Cover letter uses cover.cls", "\\documentclass[]{cover}" in cover_tex, "")
    add(
        "consistency",
        "Claude Code named if AI tooling mentioned",
        True if "Claude Code" not in cover_tex else "Claude Code" in cover_tex,
        "",
    )
    add("quality", "Balanced LaTeX braces in CV", cv_tex.count("{") == cv_tex.count("}"), "")
    add("quality", "Balanced LaTeX braces in cover", cover_tex.count("{") == cover_tex.count("}"), "")
    add(
        "quality",
        "Cover salutation present",
        bool(re.search(r"lettercontent\{[^}]{5,}", cover_tex)),
        "",
    )
    echo_comp = re.findall(r"\\cvskillcategory\{([^}]+)\}\{\1\}", cv_tex) or re.findall(
        r"\\textbf\{([^}]+)\}:\s*\1\b",
        cv_tex,
    )
    add(
        "quality",
        "No echo competencies (X: X)",
        len(echo_comp) == 0,
        ", ".join(echo_comp[:3]) if echo_comp else "",
    )
    _add_language_check(
        add, job, cv_tex, fmt="latex", llm_degraded=_is_llm_degraded(tailoring_decisions)
    )
    _add_pdf_checks(add, pdf_files, pdf_checks, fmt="latex")
    return _finalize(items)


def _run_html_checklist(
    *,
    job: JobParsed,
    cv_html: str,
    cover_html: str,
    profile_md: str,
    evaluation: FitEvaluation,
    reviewer: ReviewerResult,
    pdf_files: List[str],
    pdf_checks: List[str],
    job_targets: dict,
    llm_degraded: bool = False,
) -> dict:
    items: List[dict] = []
    settings = get_settings()
    min_coverage = float(getattr(settings, "ats_min_keyword_coverage", 0.70))

    def add(category: str, label: str, passed: bool, note: str = "") -> None:
        items.append({"category": category, "label": label, "pass": passed, "note": note})

    _add_shared_factual_targeting(
        add,
        job,
        cv_html,
        cover_html,
        evaluation,
        profile_md,
        fmt="html",
        job_targets=job_targets,
    )
    _add_ats_checks(
        add,
        cv_html,
        profile_md,
        job_targets,
        min_coverage=min_coverage,
        llm_degraded=llm_degraded,
    )
    add(
        "consistency",
        "CV uses article template",
        "<section id=\"summary\">" in cv_html and "<header>" in cv_html,
        "HTML CV template",
    )
    add(
        "consistency",
        "Cover letter uses cover.cls",
        'class="cover-letter"' in cover_html,
        "HTML cover template",
    )
    add(
        "consistency",
        "Claude Code named if AI tooling mentioned",
        True if "Claude Code" not in cover_html else "Claude Code" in cover_html,
        "",
    )
    add(
        "quality",
        "Cover salutation present",
        bool(re.search(r"<p>\s*Dear\s+[^<]{2,}</p>", cover_html, re.I))
        or bool(re.search(r"<p>[^<]{5,}</p>", cover_html)),
        "",
    )
    echo_comp = _html_echo_competencies(cv_html)
    add(
        "quality",
        "No echo competencies (X: X)",
        len(echo_comp) == 0,
        ", ".join(echo_comp[:3]) if echo_comp else "",
    )
    _add_language_check(add, job, cv_html, fmt="html", llm_degraded=llm_degraded)
    _add_pdf_checks(add, pdf_files, pdf_checks, fmt="html")

    truth = build_skill_truth_index(profile_md=profile_md, settings=settings)
    truth_violations = truth.check_text(html_to_plain_text(cv_html))
    ats_meta = compute_ats_score(
        html=cv_html,
        job_targets=job_targets,
        truth_violations=truth_violations,
        min_coverage=min_coverage,
    )
    return _finalize(items, ats=ats_meta, truth_violations=truth_violations)


def _add_shared_factual_targeting(
    add,
    job: JobParsed,
    cv_content: str,
    cover_content: str,
    evaluation: FitEvaluation,
    profile_md: str,
    *,
    fmt: str,
    job_targets: Optional[dict] = None,
) -> None:
    targets = job_targets or {}
    add("factual", "Company/role extracted from posting", job.company != "Unknown", job.company)
    if fmt == "html":
        add(
            "factual",
            "Contact details present in CV",
            _html_contact_present(cv_content, profile_md),
            "",
        )
    else:
        add(
            "factual",
            "Contact details present in CV",
            "\\cvheader{" in cv_content or "\\email{" in cv_content,
            "",
        )
    add(
        "factual",
        "No obvious fabricated placeholder text",
        "email@example.com" not in cv_content and "Candidate" not in cv_content[:200],
        "",
    )
    add(
        "targeting",
        "Role mentioned in CV profile statement",
        _role_keywords_present(cv_content, job.role) if job.role else True,
        "",
    )
    must = [str(k) for k in (targets.get("must_have_keywords") or []) if k]
    cv_low = cv_content.lower()
    if must:
        hits = sum(1 for k in must[:8] if _keyword_in_text(k, cv_low))
        add(
            "targeting",
            "Posting keywords reflected in CV (ATS heuristic)",
            hits >= 2,
            f"{hits} keyword hits in CV",
        )
    elif not _linkedin_body_usable(job.raw_text or ""):
        add(
            "targeting",
            "Posting keywords reflected in CV (ATS heuristic)",
            True,
            "skipped (chrome-only posting)",
        )
    else:
        posting_tokens = [
            w
            for w in re.findall(r"[a-ząćęłńóśźż]{4,}", (job.raw_text or "").lower())
            if w not in _LINKEDIN_CHROME_TOKENS
            and w not in ("oraz", "praca", "team", "work", "with", "your", "that", "this")
        ][:12]
        if posting_tokens:
            hits = sum(1 for t in posting_tokens[:8] if t in cv_low)
            add(
                "targeting",
                "Posting keywords reflected in CV (ATS heuristic)",
                hits >= 2,
                f"{hits} keyword hits in CV",
            )
    add(
        "targeting",
        "Company mentioned in cover letter",
        _cover_mentions_company(job, cover_content),
        "",
    )
    add(
        "targeting",
        "Evaluation completed before draft",
        evaluation.overall_fit in ("strong", "moderate", "weak"),
        evaluation.overall_fit,
    )


def _html_contact_present(cv_html: str, profile_md: str) -> bool:
    if "<header>" not in cv_html:
        return False
    header_m = re.search(r"<header>[\s\S]*?</header>", cv_html, re.I)
    block = header_m.group(0) if header_m else cv_html
    if "@" in block or re.search(r"\+\d", block):
        return True
    email_m = re.search(r"- \*\*Email:\*\* (.+)", profile_md)
    if email_m and email_m.group(1).strip() in block:
        return True
    return False


def _add_ats_checks(
    add,
    cv_html: str,
    profile_md: str,
    job_targets: dict,
    *,
    min_coverage: float,
    llm_degraded: bool = False,
) -> None:
    plain = html_to_plain_text(cv_html)
    css_block = cv_html
    style_m = re.search(r"<style>([\s\S]*?)</style>", cv_html, re.I)
    if style_m:
        css_block = style_m.group(1)

    add(
        "ats",
        "ATS layout (no table/grid/float)",
        "<table" not in cv_html.lower()
        and not re.search(r"display\s*:\s*grid", css_block, re.I)
        and not re.search(r"float\s*:\s*(left|right)", css_block, re.I),
        "",
    )
    add(
        "ats",
        "Plain-text section order (summary → skills → experience → education)",
        section_order_valid(cv_html),
        "",
    )

    coverage = ats_keyword_coverage(job_targets, plain)
    ratio = coverage["coverage_ratio"]
    if job_targets.get("must_have_keywords"):
        add(
            "ats",
            f"Keyword coverage ≥ {min_coverage:.0%}",
            ratio >= min_coverage,
            f"{ratio:.0%} ({len(coverage['hits'])}/{coverage['must_have_count']})",
        )
    else:
        add("ats", "Keyword coverage (no targets extracted)", True, "skipped")

    truth = build_skill_truth_index(profile_md=profile_md)
    violations = truth.check_text(plain)
    add(
        "ats",
        "Truth guard — no forbidden technologies",
        len(violations) == 0,
        ", ".join(violations[:4]) if violations else "",
    )

    summary_m = re.search(
        r'<section id="summary">.*?<p>([^<]+)</p>',
        cv_html,
        re.S | re.I,
    )
    summary_text = summary_m.group(1) if summary_m else plain[:600]
    role_ok = bool(summary_text.strip())
    kw_in_lead = 0
    if job_targets.get("must_have_keywords"):
        hay = f"{summary_text} {plain[:600]}".lower()
        kw_in_lead = sum(
            1
            for k in (job_targets.get("must_have_keywords") or [])[:8]
            if _keyword_in_text(str(k), hay)
        )
    add(
        "ats",
        "Summary scan (role + keywords in first 600 chars)",
        role_ok and (kw_in_lead >= 2 or not job_targets.get("must_have_keywords")),
        f"{kw_in_lead} keyword hits in lead" if job_targets.get("must_have_keywords") else "",
    )

    bullets = experience_bullets_from_html(cv_html or "")
    bq = bullet_quality_ratio(bullets)
    if llm_degraded:
        add(
            "ats",
            "Bullet quality (result verbs ≥ 60%)",
            True,
            f"skipped (LLM fallback); {bq:.0%}" if bullets else "skipped (LLM fallback)",
        )
    else:
        add(
            "ats",
            "Bullet quality (result verbs ≥ 60%)",
            not bullets or bq >= 0.6,
            f"{bq:.0%}" if bullets else "no bullets",
        )


def _html_echo_competencies(cv_html: str) -> List[str]:
    echo: List[str] = []
    for m in re.finditer(r'<strong>([^<:]+):</strong>\s*([^<\n]+)', cv_html):
        category = m.group(1).strip()
        detail = m.group(2).strip()
        if category.lower() == detail.lower():
            echo.append(category)
    return echo


def _add_language_check(
    add,
    job: JobParsed,
    cv_content: str,
    *,
    fmt: str,
    llm_degraded: bool = False,
) -> None:
    if job.language != "en":
        return
    if llm_degraded:
        add("quality", "CV language matches posting", True, "skipped (LLM fallback)")
        return
    from app.services.cv.language import text_looks_polish

    pl_bits: List[str] = []
    if fmt == "latex":
        exp_m = re.search(
            r"\\cvsection\{Professional Experience\}(.*?)\\cvsection\{",
            cv_content,
            re.S,
        ) or re.search(
            r"\\section\{Professional Experience\}(.*?)\\section\{",
            cv_content,
            re.S,
        )
        exp_tex = exp_m.group(1) if exp_m else ""
        summary_m = re.search(
            r"\\cvsection\{Professional Summary\}[\s\S]*?\n([^\n\\]+)",
            cv_content,
            re.S,
        ) or re.search(
            r"\\section\{Professional Summary\}\s*\n([^\n\\]+)",
            cv_content,
            re.S,
        ) or re.search(
            r"\\section\{Professional Summary\}.*?\\small\{([^}]+)\}",
            cv_content,
            re.S,
        )
        if summary_m and text_looks_polish(summary_m.group(1)):
            pl_bits.append("summary")
        for bullet in re.findall(r"\\item ([^\n]+)", exp_tex):
            if text_looks_polish(bullet):
                pl_bits.append("experience")
                break
    else:
        summary_m = re.search(
            r'<section id="summary">.*?<p>([^<]+)</p>',
            cv_content,
            re.S | re.I,
        )
        if summary_m and text_looks_polish(summary_m.group(1)):
            pl_bits.append("summary")
        exp_m = re.search(r'<section id="experience">(.*?)</section>', cv_content, re.S | re.I)
        exp_html = exp_m.group(1) if exp_m else ""
        for bullet in re.findall(r"<li>([^<]+)</li>", exp_html):
            if text_looks_polish(bullet):
                pl_bits.append("experience")
                break
    add(
        "quality",
        "CV language matches posting",
        len(pl_bits) == 0,
        ", ".join(pl_bits) if pl_bits else "",
    )


def _add_pdf_checks(add, pdf_files: List[str], pdf_checks: List[str], *, fmt: str) -> None:
    for check in pdf_checks:
        add("pdf", check.replace("pass: ", "").replace("fail: ", ""), check.startswith("pass:"), check)
    if not pdf_files:
        hint = (
            "Brak PDF — zainstaluj Playwright lub sprawdź logi"
            if fmt == "html"
            else "Brak PDF — zainstaluj LaTeX lub sprawdź logi"
        )
        add("pdf", "PDF files generated", False, hint)


def _finalize(
    items: List[dict],
    *,
    ats: Optional[dict] = None,
    truth_violations: Optional[List[str]] = None,
) -> dict:
    passed = sum(1 for i in items if i["pass"])
    result = {
        "passed": passed,
        "total": len(items),
        "all_pass": passed == len(items),
        "items": items,
        "renderer": "html" if any(
            i.get("note") in ("HTML CV template", "HTML cover template") for i in items
        ) else "latex",
    }
    if ats is not None:
        result["ats_score"] = ats.get("ats_score", 0)
        result["keyword_coverage"] = ats.get("coverage", {})
        result["missing_keywords"] = (ats.get("coverage") or {}).get("missing_keywords", [])
        result["ats_notes"] = ats.get("notes", [])
        result["bullet_quality_ratio"] = ats.get("bullet_quality_ratio")
    if truth_violations is not None:
        result["truth_violations"] = truth_violations
    return result


def summarize_tailoring(job: JobParsed, reviewer: ReviewerResult, evaluation: FitEvaluation) -> List[str]:
    decisions = [
        f"Emphasis on {job.role} requirements at {job.company}",
        f"Overall fit assessed as {evaluation.overall_fit}",
    ]
    if reviewer.company_research_notes:
        decisions.append(f"Company angle: {reviewer.company_research_notes[:120]}")
    narrative = reviewer.narrative or {}
    for key, val in list(narrative.items())[:2]:
        if val:
            decisions.append(f"Reviewer ({key}): {str(val)[:100]}")
    return decisions[:5]
