"""ATS keyword coverage, plain-text extraction, and bullet highlighting."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import List, Optional

from markupsafe import Markup, escape

_SECTION_ORDER = ("summary", "skills", "experience", "education")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: List[str] = []
        self._section_ids: List[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "section":
            for k, v in attrs:
                if k == "id" and v:
                    self._section_ids.append(v)

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._parts.append(data)

    def plain_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._parts)).strip()

    def section_order_ok(self) -> bool:
        ids = [s for s in self._section_ids if s in _SECTION_ORDER]
        if len(ids) < 2:
            return True
        ranks = [_SECTION_ORDER.index(s) for s in ids if s in _SECTION_ORDER]
        return ranks == sorted(ranks)


def html_to_plain_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        return re.sub(r"<[^>]+>", " ", html or "")
    return parser.plain_text()


def experience_bullets_from_html(html: str) -> List[str]:
    """Extract experience-section bullets only (exclude skills list items)."""
    m = re.search(r'<section id="experience">(.*?)</section>', html or "", re.S | re.I)
    if not m:
        return []
    bullets: List[str] = []
    for li in re.finditer(r"<li>(.*?)</li>", m.group(1), re.S | re.I):
        bullets.append(re.sub(r"<[^>]+>", "", li.group(1)))
    return bullets


def section_order_valid(html: str) -> bool:
    parser = _TextExtractor()
    try:
        parser.feed(html or "")
    except Exception:
        return True
    return parser.section_order_ok()


def _keyword_in_text(keyword: str, hay: str) -> bool:
    k = (keyword or "").strip().lower()
    if not k or len(k) < 2:
        return False
    if k in hay:
        return True
    parts = [p.strip() for p in re.split(r"[\s/&]+", k) if len(p.strip()) >= 3]
    if parts and all(p in hay for p in parts[:3]):
        return True
    return False


def ats_keyword_coverage(job_targets: dict, cv_plain_text: str) -> dict:
    must = [str(k) for k in (job_targets.get("must_have_keywords") or []) if k]
    hay = (cv_plain_text or "").lower()
    hits = [k for k in must if _keyword_in_text(k, hay)]
    missing = [k for k in must if k not in hits]
    ratio = (len(hits) / len(must)) if must else 1.0
    return {
        "coverage_ratio": round(ratio, 3),
        "hits": hits,
        "missing_keywords": missing,
        "must_have_count": len(must),
    }


def highlight_keywords_in_text(text: str, keywords: List[str]) -> Markup:
    """Wrap phrases already present in text with <strong> (ATS recruiter scan)."""
    if not text or not keywords:
        return Markup(escape(text))
    safe = str(escape(text))
    seen: set[str] = set()
    for kw in sorted(keywords, key=len, reverse=True):
        k = (kw or "").strip()
        if len(k) < 3 or k.lower() in seen:
            continue
        seen.add(k.lower())
        pattern = re.compile(re.escape(k), re.I)
        safe = pattern.sub(lambda m: f"<strong>{m.group(0)}</strong>", safe)
    return Markup(safe)


def collect_highlight_keywords(job_targets: dict, truth_allowed: Optional[set] = None) -> List[str]:
    keys: List[str] = []
    for field in ("must_have_keywords", "tools_explicit", "nice_to_have_keywords"):
        keys.extend(str(k) for k in (job_targets.get(field) or []) if k)
    for norm in job_targets.get("normalized_skills") or []:
        if isinstance(norm, dict):
            term = norm.get("candidate_term") or norm.get("posting_term")
            if term:
                keys.append(str(term))
    if truth_allowed:
        keys = [k for k in keys if any(_keyword_in_text(k, t) for t in truth_allowed) or len(k) < 4]
    # dedupe preserve order
    out: List[str] = []
    for k in keys:
        lk = k.lower()
        if lk not in {x.lower() for x in out}:
            out.append(k)
    return out[:20]


_RESULT_VERBS_EN = re.compile(
    r"\b(led|managed|delivered|reduced|increased|improved|achieved|built|scaled|"
    r"implemented|optimized|drove|established|grew|ensured|defined|monitored|"
    r"developed|oversaw|overseen|co-led|co-leading|co-creating|building|"
    r"providing|supporting|coordinating|organizing|standardized|"
    r"coordinated|communicated|closed|planned|executed|reported|facilitated)\b",
    re.I,
)
_RESULT_VERBS_PL = re.compile(
    r"\b(prowadził|prowadziła|prowadziłem|prowadziłam|zarządzał|zarządzała|zarządzałem|"
    r"zarządzałam|wdrożył|wdrożyła|wdrożyłem|wdrożyłam|zwiększył|zwiększyła|obniżył|"
    r"obniżyła|osiągnął|osiągnęła|zoptymalizował|zoptymalizowała|nadzorował|nadzorowała|"
    r"definiował|definiowała|monitorował|monitorowała|zbudował|zbudowała|budował|budowała|"
    r"opracował|opracowała|koordynował|koordynowała|reprezentował|reprezentowała)\w*\b",
    re.I,
)
_PL_BULLET_ACTION_NOUN = re.compile(
    r"^(Pozyskiwanie|Prowadzenie|Budowa|Wdrożenie|Opracowanie|Zarządzanie|Nadzorowanie|"
    r"Nadzór|Definiowanie|Monitorowanie|Koordynowanie|Tworzenie|Odpowiedzialność|Udział|"
    r"Uczestnictwo|Współodpowiedzialność)\b",
    re.I,
)


def bullet_quality_ratio(bullets: List[str]) -> float:
    if not bullets:
        return 0.0
    good = sum(
        1
        for b in bullets
        if _RESULT_VERBS_EN.search(b)
        or _RESULT_VERBS_PL.search(b)
        or _PL_BULLET_ACTION_NOUN.search(b.strip())
    )
    return good / len(bullets)


def compute_ats_score(
    *,
    html: str,
    job_targets: dict,
    truth_violations: List[str],
    min_coverage: float = 0.70,
) -> dict:
    plain = html_to_plain_text(html)
    coverage = ats_keyword_coverage(job_targets, plain)
    layout_ok = section_order_valid(html)
    css_grid = bool(re.search(r"display\s*:\s*grid", html, re.I))
    css_float = bool(re.search(r"float\s*:\s*(left|right)", html, re.I))
    has_table = "<table" in (html or "").lower()

    score = 100
    notes: List[str] = []
    if coverage["coverage_ratio"] < min_coverage:
        score -= int((min_coverage - coverage["coverage_ratio"]) * 40)
        notes.append(f"coverage {coverage['coverage_ratio']:.0%}")
    if truth_violations:
        score -= min(30, 10 * len(truth_violations))
        notes.append(f"truth violations: {len(truth_violations)}")
    if not layout_ok:
        score -= 10
        notes.append("section order")
    if css_grid or css_float or has_table:
        score -= 15
        notes.append("layout risk")

    bullets = experience_bullets_from_html(html)
    bq = bullet_quality_ratio(bullets)
    if bullets and bq < 0.6:
        score -= 10
        notes.append(f"bullet quality {bq:.0%}")

    return {
        "ats_score": max(0, min(100, score)),
        "coverage": coverage,
        "plain_text_preview": plain[:400],
        "layout_ok": layout_ok and not css_grid and not css_float and not has_table,
        "bullet_quality_ratio": round(bq, 2) if bullets else None,
        "notes": notes,
    }
