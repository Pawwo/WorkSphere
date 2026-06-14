"""Skill truth index and post-LLM sanitization (ATS rule 4.5 — no fabricated tools)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional, Set

from app.config import Settings, get_settings
from app.services.cv.competencies import parse_competencies_from_master
from app.services.cv.identity import parse_certifications_from_profile
from app.services.cv.master import resolve_master_cv_text
from app.services.cv_import_service import _list_items, _section_slice

# Tools often hallucinated when absent from candidate profile
_WATCHLIST_TOOLS: tuple[str, ...] = (
    "zapier",
    "make.com",
    "power bi",
    "tableau",
    "salesforce",
    "hubspot",
    "sap s/4hana",
    "sap erp",
    "kubernetes",
    "terraform",
    "azure devops",
    "aws lambda",
    "snowflake",
    "databricks",
)

_GENERIC_REPLACEMENTS: dict[str, str] = {
    "zapier": "automatyzacja procesów biznesowych",
    "make.com": "automatyzacja workflow",
    "power bi": "analiza danych operacyjnych",
    "tableau": "analiza danych i raportowanie",
    "salesforce": "CRM i zarządzanie relacjami z klientami",
    "hubspot": "CRM i marketing automation",
    "sap s/4hana": "systemy ERP klasy enterprise",
    "sap erp": "systemy ERP",
    "kubernetes": "infrastruktura kontenerowa",
    "terraform": "infrastruktura jako kod",
    "azure devops": "CI/CD i DevOps",
    "aws lambda": "usługi chmurowe",
    "snowflake": "hurtownie danych",
    "databricks": "platformy analityczne",
}

ALLOWED_GENERIC_PHRASES: frozenset[str] = frozenset(
    {
        "automatyzacja procesów biznesowych",
        "automatyzacja workflow",
        "integracje api",
        "analiza danych",
        "analiza danych operacyjnych",
        "raportowanie kpi",
        "transformacja cyfrowa",
        "zarządzanie projektami",
        "project management",
        "stakeholder management",
        "business process automation",
        "api integrations",
        "data analysis",
        "workflow automation",
    }
)

_TOKEN_RE = re.compile(
    r"\b([A-Za-z][A-Za-z0-9+#./-]{1,30})\b",
)


def _norm_token(token: str) -> str:
    return re.sub(r"\s+", " ", (token or "").strip().lower())


def _tokens_from_text(text: str) -> Set[str]:
    if not text:
        return set()
    out: Set[str] = set()
    low = text.lower()
    for tool in _WATCHLIST_TOOLS:
        if tool in low:
            out.add(tool)
    for m in _TOKEN_RE.finditer(text):
        t = _norm_token(m.group(1))
        if len(t) >= 2:
            out.add(t)
    for chunk in re.split(r"[,;|•\n\-–—]", text):
        c = _norm_token(chunk)
        if 2 <= len(c) <= 40:
            out.add(c)
    return out


def _section_tokens(text: str, *headers: str) -> Set[str]:
    tokens: Set[str] = set()
    for i, header in enumerate(headers):
        end = headers[i + 1] if i + 1 < len(headers) else None
        block = _section_slice(text, header, *( [end] if end else []))
        if not block and i == 0:
            continue
        if not block:
            block = _section_slice(text, header, "DOŚWIADCZENIE", "EDUCATION", "WYKSZTAŁCENIE")
        tokens |= _tokens_from_text(block)
        for item in _list_items(block, max_items=80):
            tokens |= _tokens_from_text(item)
    return tokens


@dataclass
class SkillTruthIndex:
    allowed_tools: Set[str] = field(default_factory=set)
    violations: List[str] = field(default_factory=list)

    def is_allowed(self, term: str) -> bool:
        t = _norm_token(term)
        if not t:
            return True
        if t in self.allowed_tools:
            return True
        for allowed in self.allowed_tools:
            if allowed == t:
                return True
            # Avoid false positives (e.g. "za" ⊂ "zapier", "erp" ⊂ "sap erp").
            if len(t) < 4 or len(allowed) < 4:
                continue
            if t in allowed or allowed in t:
                return True
        return False

    def _watchlist_phrase_allowed(self, phrase: str) -> bool:
        p = _norm_token(phrase)
        if not p:
            return True
        if p in self.allowed_tools:
            return True
        for allowed in self.allowed_tools:
            if allowed == p:
                return True
            if len(p) >= 5 and len(allowed) >= len(p) and p in allowed:
                if re.search(re.escape(p), allowed):
                    return True
        return False

    def sample_for_prompt(self, limit: int = 40) -> str:
        items = sorted(self.allowed_tools)[:limit]
        return ", ".join(items)

    def check_text(self, text: str) -> List[str]:
        found: List[str] = []
        low = (text or "").lower()
        for tool in _WATCHLIST_TOOLS:
            if tool in low and not self._watchlist_phrase_allowed(tool):
                found.append(tool)
        return found

    def sanitize_text(self, text: str, *, strict: bool = True) -> tuple[str, List[str]]:
        if not text:
            return text, []
        violations = self.check_text(text)
        out = text
        for tool in violations:
            repl = _GENERIC_REPLACEMENTS.get(tool, "obszar kompetencji zgodny z profilem")
            out = re.sub(re.escape(tool), repl, out, flags=re.I)
            self.violations.append(f"replaced:{tool}")
        if strict:
            for v in violations:
                if v not in [x.replace("replaced:", "") for x in self.violations]:
                    pass
        return out, violations

    def sanitize_dict(self, data: dict, *, strict: bool = True) -> dict:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if isinstance(out.get("profile_statement"), str):
            out["profile_statement"], _ = self.sanitize_text(out["profile_statement"], strict=strict)
        for key in ("opening", "body", "motivation", "closing", "salutation"):
            if isinstance(out.get(key), str):
                out[key], _ = self.sanitize_text(out[key], strict=strict)
        if isinstance(out.get("bullets"), list):
            out["bullets"] = [
                self.sanitize_text(str(b), strict=strict)[0] for b in out["bullets"] if b
            ]
        if isinstance(out.get("competencies"), list):
            out["competencies"] = [
                self.sanitize_text(str(c), strict=strict)[0] for c in out["competencies"] if c
            ]
        entries = out.get("experience_entries")
        if isinstance(entries, list):
            cleaned = []
            for e in entries:
                if not isinstance(e, dict):
                    continue
                entry = dict(e)
                bullets = entry.get("bullets")
                if isinstance(bullets, list):
                    entry["bullets"] = [
                        self.sanitize_text(str(b), strict=strict)[0] for b in bullets if b
                    ]
                cleaned.append(entry)
            out["experience_entries"] = cleaned
        kw = out.get("competency_keywords")
        if isinstance(kw, list):
            out["competency_keywords"] = [k for k in kw if self.is_allowed(str(k))]
        return out

    def filter_keywords(self, keywords: Iterable[str]) -> List[str]:
        return [k for k in keywords if self.is_allowed(str(k)) or _norm_token(str(k)) in ALLOWED_GENERIC_PHRASES]


def build_skill_truth_index(
    *,
    profile_md: str = "",
    settings: Optional[Settings] = None,
) -> SkillTruthIndex:
    settings = settings or get_settings()
    master = resolve_master_cv_text(settings)
    allowed: Set[str] = set()

    allowed |= _tokens_from_text(profile_md)
    allowed |= _tokens_from_text(master)

    for header in (
        "KLUCZOWE KOMPETENCJE",
        "ATS KEYWORDS",
        "Słowa kluczowe ATS",
        "UMIEJĘTNOŚCI",
        "TECHNICAL SKILLS",
        "CERTYFIKATY",
        "CERTIFICATIONS",
    ):
        block = _section_slice(
            master,
            header,
            "DOŚWIADCZENIE",
            "OBSZARY",
            "WYKSZTAŁCENIE",
            "EDUCATION",
        )
        allowed |= _tokens_from_text(block)
        for item in _list_items(block, max_items=60):
            allowed |= _tokens_from_text(item)

    for comp in parse_competencies_from_master(master):
        allowed |= _tokens_from_text(comp)

    for cert in parse_certifications_from_profile(profile_md):
        allowed |= _tokens_from_text(cert)

    tech = _section_slice(profile_md, "## Technical Skills", "## ", "CERTIFICATIONS")
    allowed |= _tokens_from_text(tech)

    # Normalize common variants present in real profiles
    for alias in ("jira", "confluence", "odoo", "python", "erp", "agile", "scrum", "bpmn", "kpi"):
        if any(alias in t for t in allowed):
            allowed.add(alias)

    return SkillTruthIndex(allowed_tools=allowed)
