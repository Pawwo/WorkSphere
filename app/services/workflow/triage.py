"""Keyword-based job triage scoring."""

from __future__ import annotations

import re

from app.services.keyword_triage import is_reject_job
from app.services.salary_service import SalaryService

STRONG_KEYWORDS = (
    r"\bcoo\b",
    r"chief operating",
    r"operations director",
    r"global operations",
    r"head of operations",
    r"general manager",
    r"capability centre",
    r"transformation manager",
    r"odoo",
    r"\berp\b",
    r"head of lean",
    r"optymalizacji proces",
    r"dywizji aplikacji biznesowych",
    r"supply chain director",
    r"country manager",
)

GOOD_KEYWORDS = (
    r"project manager",
    r"program manager",
    r"data program manager",
    r"menedżer",
    r"manager",
    r"director",
    r"head of",
    r"ai ",
    r"bezpieczeństwa grupy",
    r"finance project manager",
    r"team leader",
    r"business analyst",
)

def score_job(title: str, company: str) -> tuple[int, str]:
    if is_reject_job(title, company):
        return -100, "reject_keyword"

    blob = f"{title} {company}".lower()
    blob = re.sub(r"&amp;", "&", blob)

    score = 0
    reasons: list[str] = []
    for pat in STRONG_KEYWORDS:
        if re.search(pat, blob, re.I):
            score += 30
            reasons.append(f"strong:{pat}")
    for pat in GOOD_KEYWORDS:
        if re.search(pat, blob, re.I):
            score += 10
            reasons.append(f"good:{pat}")

    if "operations" in blob or "operating" in blob:
        score += 25
        reasons.append("operations")
    if "transformation" in blob or "lean" in blob:
        score += 15
        reasons.append("transformation")

    reason = ", ".join(reasons[:4]) if reasons else "generic"
    return score, reason


def salary_triage_penalty(job: dict, salary_svc: SalaryService) -> tuple[int, str]:
    if job.get("salary_meets_threshold") is False:
        med = job.get("salary_b2b_monthly") or 0
        if med < salary_svc.threshold_pln * 0.7:
            return -40, "salary_far_below_b2b_threshold"
        return -25, "salary_below_b2b_threshold"
    if job.get("salary_source") == "estimated" and job.get("salary_meets_threshold") is False:
        return -15, "salary_estimated_below_threshold"
    return 0, ""
