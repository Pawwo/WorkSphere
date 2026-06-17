"""Extract lightweight fit signals from job posting and candidate profile.

This is intentionally heuristic and fast: it's used to enrich LLM prompts and
to protect against false-negative quick_fit='low' decisions.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


def _has(pat: str, text: str) -> bool:
    return bool(re.search(pat, text, re.I))


def extract_job_signals(*, title: str, description: str) -> Dict[str, Any]:
    text = f"{title}\n{description}".strip()
    t = text.lower()

    signals: Dict[str, Any] = {"flags": [], "matches": []}

    role_flags = []
    if _has(r"\b(delivery lead|technical delivery manager|delivery manager)\b", t):
        role_flags.append("delivery_lead")
    if _has(r"\b(program|project)\s+(manager|lead)\b", t):
        role_flags.append("pm_program")
    if _has(r"\b(head of|director|vp|chief)\b", t):
        role_flags.append("senior_leadership")

    env_flags = []
    if _has(r"\b(sdlc|software delivery lifecycle)\b", t):
        env_flags.append("sdlc")
    if _has(r"\b(engineering|engineers|engineering pods|pod[- ]based)\b", t):
        env_flags.append("engineering")
    if _has(r"\b(cross[- ]functional|pod[- ]based|ways of working)\b", t):
        env_flags.append("cross_functional")

    ai_flags = []
    if _has(r"\b(ai|artificial intelligence|generative ai|agentic)\b", t):
        ai_flags.append("ai_adoption")
    if _has(r"\b(claude|copilot)\b", t):
        ai_flags.append("ai_tools")

    capability_flags = []
    if _has(r"\b(capability|capability frameworks?|career development|progression)\b", t):
        capability_flags.append("capability_frameworks")
    if _has(r"\b(process improvements?|process improvement|standards|best practices)\b", t):
        capability_flags.append("process_improvement")
    if _has(r"\b(hiring|organisational design|organizational design)\b", t):
        capability_flags.append("hiring_org_design")

    domain_flags = []
    if _has(r"\b(fintech|financial services|investment banking|capital markets)\b", t):
        domain_flags.append("financial_services")

    for flag in role_flags + env_flags + ai_flags + capability_flags + domain_flags:
        signals["flags"].append(flag)

    # Keep a compact, human-readable view for logs/UI.
    signals["high_signal"] = sorted(
        set(role_flags + env_flags + ai_flags + capability_flags), key=str
    )
    signals["domain"] = domain_flags
    return signals


def extract_profile_signals(profile_excerpt: str) -> Dict[str, Any]:
    t = (profile_excerpt or "").lower()
    flags: List[str] = []

    if _has(r"\b(coo|chief operating officer)\b", t):
        flags.append("coo")
    if _has(r"\b(operations|operating)\b", t):
        flags.append("operations")
    if _has(r"\b(delivery|project manager|program manager)\b", t):
        flags.append("delivery_pm")
    if _has(r"\b(odoo|erp)\b", t):
        flags.append("erp_odoo")
    if _has(r"\b(ai|generative ai|agentic|llm|chatbot)\b", t):
        flags.append("ai")
    if _has(r"\b(claude|copilot)\b", t):
        flags.append("ai_tools")
    if _has(r"\b(sdlc|software delivery|developers|qa)\b", t):
        flags.append("sdlc_engineering")
    if _has(r"\b(capability|kpi|framework|career development)\b", t):
        flags.append("capability")

    return {"flags": sorted(set(flags))}


def strong_job_signal(signals: Dict[str, Any] | None) -> bool:
    if not signals:
        return False
    flags = set(signals.get("flags") or [])
    # A minimal, conservative definition: role + environment + (AI or capability)
    role = bool(flags & {"delivery_lead", "pm_program"})
    env = bool(flags & {"sdlc", "engineering", "cross_functional"})
    plus = bool(flags & {"ai_adoption", "capability_frameworks", "process_improvement"})
    return role and env and plus

