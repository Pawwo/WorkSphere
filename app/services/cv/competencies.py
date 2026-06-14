"""CV competencies parsing, validation, and merge."""
from __future__ import annotations

import re
from typing import List, Optional

from app.services.cv_import_service import _list_items, _section_slice

_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Executive Leadership",
        (
            "coo",
            "chief operating",
            "leadership",
            "strategic",
            "organizational",
            "team leadership",
            "change management",
            "p&l",
            "budget",
            "cross-functional",
            "executive",
        ),
    ),
    (
        "Operational Excellence & Scaling",
        (
            "operational excellence",
            "operations scaling",
            "process",
            "bpmn",
            "workflow",
            "kpi",
            "automation",
            "analytics",
            "resource planning",
            "data-driven",
            "delivery operations",
            "scaling",
        ),
    ),
    (
        "Tech Infrastructure & SaaS",
        (
            "saas",
            "erp",
            "odoo",
            "hosting",
            "infrastructure",
            "agile",
            "scrum",
            "kanban",
            "ci/cd",
            "technology services",
            "high-availability",
            "digital service",
        ),
    ),
    (
        "AI & Automation Capabilities",
        (
            "ai ",
            "artificial intelligence",
            "llm",
            "rag",
            "agent",
            "generative",
            "eu ai act",
            "iso 42001",
            "nist",
            "human-in-the-loop",
            "python",
            "machine learning",
        ),
    ),
    (
        "Commercial & Growth",
        (
            "business development",
            "sales",
            "customer",
            "stakeholder",
            "negotiation",
            "go-to-market",
            "commercial",
            "retention",
            "contract",
        ),
    ),
]

_ECHO_BLOCKLIST = re.compile(
    r"^(ultahost|kraków|krakow|warszawa|szczecin|chief operating officer|coo|"
    r"zarządzanie operacjami|strategia biznesowa|rozwój firmy)$",
    re.I,
)


def _split_competency(line: str) -> tuple[str, str]:
    if ":" not in line:
        return line.strip(), ""
    label, _, details = line.partition(":")
    return label.strip(), details.strip()


def normalize_competency_line(item: object) -> str:
    """Convert LLM dict / repr strings to 'Category: details' lines."""
    if isinstance(item, dict):
        category = str(item.get("category") or item.get("name") or item.get("title") or "").strip()
        detail = str(
            item.get("description") or item.get("detail") or item.get("items") or ""
        ).strip()
        if category and detail:
            return f"{category}: {detail}"
        if category:
            return category
    s = (str(item) if item is not None else "").strip()
    if not s:
        return ""
    if s.startswith("{") and "category" in s:
        import ast

        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, dict):
                return normalize_competency_line(parsed)
        except (SyntaxError, ValueError):
            pass
        cat_m = re.search(r"""['"]category['"]\s*:\s*['"]([^'"]+)['"]""", s)
        desc_m = re.search(r"""['"]description['"]\s*:\s*['"]([^'"]+)['"]""", s)
        if cat_m and desc_m:
            return f"{cat_m.group(1)}: {desc_m.group(1)}"
    return s


def is_valid_competency(line: str, *, blocked_keywords: Optional[set[str]] = None) -> bool:
    line = (line or "").strip()
    if not line or ":" not in line:
        return False
    label, details = _split_competency(line)
    if not label or not details:
        return False
    if label.lower() == details.lower():
        return False
    if _ECHO_BLOCKLIST.match(label):
        return False
    if blocked_keywords and label.lower() in blocked_keywords and len(details.split(",")) < 2:
        return False
    if len(details) < 8:
        return False
    return True


def sanitize_competencies(
    lines: List[str],
    *,
    blocked_keywords: Optional[set[str]] = None,
) -> List[str]:
    out: List[str] = []
    for line in lines:
        s = normalize_competency_line(line)
        if s and is_valid_competency(s, blocked_keywords=blocked_keywords):
            out.append(s)
    return out


def _assign_category(skill: str) -> str:
    low = skill.lower()
    for category, keywords in _CATEGORY_RULES:
        if any(kw in low for kw in keywords):
            return category
    return "Professional Skills"


def _group_skills_into_categories(skills: List[str], max_per_category: int = 10) -> List[str]:
    buckets: dict[str, List[str]] = {cat: [] for cat, _ in _CATEGORY_RULES}
    buckets["Professional Skills"] = []
    for skill in skills:
        cat = _assign_category(skill)
        if len(buckets[cat]) < max_per_category:
            buckets[cat].append(skill)
    out: List[str] = []
    for category, _ in _CATEGORY_RULES:
        items = buckets.get(category) or []
        if items:
            out.append(f"{category}: {', '.join(items)}")
    if buckets["Professional Skills"]:
        out.append(f"Professional Skills: {', '.join(buckets['Professional Skills'][:8])}")
    return out[:6]


def parse_competencies_from_master(text: str) -> List[str]:
    if not text:
        return []
    block = _section_slice(
        text,
        "KLUCZOWE KOMPETENCJE",
        "OBSZARY SPECJALIZACJI",
        "DOŚWIADCZENIE ZAWODOWE",
    )
    if not block:
        block = _section_slice(text, "UMIEJĘTNOŚCI", "WYKSZTAŁCENIE", "CERTYFIKATY")
    skills = _list_items(block, max_items=40)
    if len(skills) < 5:
        return []
    return _group_skills_into_categories(skills)


def _blocked_from_targets(job_targets: Optional[dict]) -> set[str]:
    if not job_targets:
        return set()
    blocked: set[str] = set()
    for key in ("must_have_keywords", "nice_to_have_keywords", "priority_themes"):
        for item in job_targets.get(key) or []:
            blocked.add(str(item).strip().lower())
    return blocked


def _weave_keywords(competencies: List[str], keywords: List[str]) -> List[str]:
    if not keywords or not competencies:
        return competencies
    woven = list(competencies)
    extras = [k for k in keywords if k and len(k) > 3][:2]
    if not extras:
        return woven
    label, details = _split_competency(woven[0])
    merged_details = details
    for kw in extras:
        if kw.lower() not in details.lower():
            merged_details = f"{merged_details}, {kw}"
    woven[0] = f"{label}: {merged_details}"
    return woven


def merge_competencies(
    baseline: List[str],
    llm_lines: List[str],
    job_targets: Optional[dict] = None,
    *,
    competency_keywords: Optional[List[str]] = None,
) -> List[str]:
    blocked = _blocked_from_targets(job_targets)
    valid_llm = sanitize_competencies(llm_lines, blocked_keywords=blocked)
    if len(valid_llm) >= 4:
        merged = valid_llm[:6]
    else:
        merged = list(baseline[:6])
    kw = [str(k).strip() for k in (competency_keywords or []) if k]
    if not kw and job_targets:
        kw = [str(k) for k in (job_targets.get("must_have_keywords") or [])[:2]]
    return _weave_keywords(merged, kw)


def role_headline_for_job(role: str) -> str:
    r = (role or "").lower()
    if "program" in r or ("project" in r and "manager" in r):
        return (role or "").strip()
    if "coo" in r or "chief operating" in r:
        return "Chief Operating Officer (COO) / Operations Director"
    if "operations" in r and "director" in r:
        return "Operations Director"
    return (role or "").strip()


def _role_keywords_present(text: str, role: str) -> bool:
    """True when summary already mentions meaningful tokens from the job role."""
    hay = (text or "").lower()
    role_l = (role or "").lower()
    if not hay or not role_l:
        return True
    if ("project" in role_l or "program" in role_l) and any(
        k in hay
        for k in (
            "operations",
            "coo",
            "chief operating",
            "program management",
            "project management",
            "delivery manager",
        )
    ):
        return True
    tokens = [
        t.strip(",.;:&")
        for t in re.split(r"[\s/&]+", role_l)
        if len(t.strip(",.;:&")) >= 4
    ]
    if not tokens:
        first = role_l.split()[0].strip(",.;:")
        return len(first) < 3 or first in hay
    return any(tok in hay for tok in tokens)


def ensure_role_in_profile_statement(profile: str, role: str, *, max_len: int = 900) -> str:
    """Ensure profile mentions the target role for ATS verification heuristics."""
    text = (profile or "").strip()
    role = (role or "").strip()
    if not role or not text:
        return text
    if _role_keywords_present(text, role):
        return text
    lead = role_headline_for_job(role) or role.split(",")[0].strip()
    prefixed = f"{lead}. {text}"
    return prefixed[:max_len] if len(prefixed) > max_len else prefixed
