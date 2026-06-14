"""Trim profile/job text for LLM calls (BC-250 Vulkan n_ctx=4096)."""

from __future__ import annotations

import html
import json
import re

from app.services.profile.language_skills import (
    _LANGUAGE_LABEL_PL,
    parse_languages_text,
)

PROFILE_MAX = 800
FRAMEWORK_MAX = 500
JOB_POSTING_MAX = 900
REVIEWER_PROFILE_MAX = 700
REVIEWER_JOB_MAX = 900
REVIEWER_TEX_MAX = 2000
CV_PROFILE_MAX = 800
CV_EXPERIENCE_BATCH_MAX = 900
CV_TARGETS_JOB_MAX = 600
CV_EXPERIENCE_BATCH_SIZE = 2
CV_TAILOR_TOP_JOBS = 4
CONTEXT_RESERVE_TOKENS = 256

_CEFR_RANK = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6, "native": 7}
_ENGLISH_GAP_RE = re.compile(
    r"english|angielsk|b1\+?|b2\+?|language proficien|język ang|jezyk ang",
    re.I,
)


def estimate_tokens(text: str) -> int:
    """Conservative estimate for Polish/English mixed text."""
    return max(1, len(text) // 2)


def safe_max_tokens(
    messages: list[dict],
    requested: int,
    *,
    n_ctx: int = 2048,
    reserve: int = CONTEXT_RESERVE_TOKENS,
) -> int:
    prompt_text = "\n".join(m.get("content", "") for m in messages)
    prompt_tokens = estimate_tokens(prompt_text)
    available = n_ctx - prompt_tokens - reserve
    return max(96, min(requested, available))


def compact_job_targets(targets: dict) -> str:
    slim = {
        "must_have_keywords": (targets.get("must_have_keywords") or [])[:10],
        "nice_to_have_keywords": (targets.get("nice_to_have_keywords") or [])[:6],
        "tools_explicit": (targets.get("tools_explicit") or [])[:8],
        "soft_skills": (targets.get("soft_skills") or [])[:6],
        "normalized_skills": (targets.get("normalized_skills") or [])[:6],
        "keyword_placement_hints": targets.get("keyword_placement_hints") or {},
        "priority_themes": (targets.get("priority_themes") or [])[:5],
        "emphasis_jobs": (targets.get("emphasis_jobs") or [])[:4],
        "profile_angle": (targets.get("profile_angle") or "")[:200],
        "avoid_framing": (targets.get("avoid_framing") or [])[:3],
    }
    return json.dumps(slim, ensure_ascii=False, separators=(",", ":"))


def _section_excerpt(text: str, header: str, max_chars: int) -> str:
    low = text.lower()
    pos = low.find(header.lower())
    if pos < 0:
        return ""
    chunk = text[pos : pos + max_chars]
    return chunk.strip()


def _extract_identity_languages_line(profile_md: str) -> str:
    for pattern in (
        r"^\s*-\s*\*\*Languages:\*\*\s*(.+)$",
        r"^\s*-\s*\*\*Języki:\*\*\s*(.+)$",
    ):
        m = re.search(pattern, profile_md, re.M | re.I)
        if m:
            return m.group(1).strip()
    return ""


def _extract_job_english_requirement(job_text: str) -> str | None:
    text = _normalize_job_posting_text(job_text)
    for pattern in (
        r"english[^.;]{0,160}?\b(a1|a2|b1\+?|b2\+?|c1\+?|c2)\b",
        r"angielski[^.;]{0,160}?\b(a1|a2|b1\+?|b2\+?|c1\+?|c2)\b",
    ):
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).upper()
    return None


def _cefr_meets(candidate: str, required: str) -> bool:
    req = required.rstrip("+").upper()
    if candidate not in _CEFR_RANK or req not in _CEFR_RANK:
        return False
    return _CEFR_RANK[candidate] >= _CEFR_RANK[req]


def language_assessment_for_eval(profile_md: str, job_raw_text: str) -> tuple[str, bool]:
    """Structured CEFR note for evaluate_fit; returns (prompt block, english_ok)."""
    lang_line = _extract_identity_languages_line(profile_md)
    entries = parse_languages_text(lang_line) if lang_line else []
    if not entries:
        return ("Brak danych o językach w profilu (sekcja Identity).", False)

    lines = ["Języki kandydata (CEFR — używaj wyłącznie tych danych):"]
    english_level: str | None = None
    for entry in entries:
        label = _LANGUAGE_LABEL_PL.get(entry.language, entry.language)
        lines.append(f"- {label}: {entry.level}")
        if entry.language == "english":
            english_level = entry.level

    required = _extract_job_english_requirement(job_raw_text)
    english_ok = False
    if english_level and required:
        english_ok = _cefr_meets(english_level, required)
        req_label = required if required.endswith("+") else f"{required}+"
        lines.append(
            f"Wymaganie angielskiego w ofercie: min. {req_label}. "
            f"Poziom kandydata: {english_level}. "
            f"Status: {'SPEŁNIONE' if english_ok else 'NIESPEŁNIONE'}."
        )
        if english_ok:
            lines.append(
                "Angielski NIE jest luką — nie wymieniaj go w gaps ani w recommendation jako brak."
            )
    elif english_level:
        lines.append(f"Poziom angielskiego kandydata: {english_level} (brak jawnego wymagania w ofercie).")
        english_ok = True

    return ("\n".join(lines), english_ok)


def sanitize_false_english_gap(parsed: dict, english_ok: bool) -> dict:
    """Remove hallucinated English gaps when CEFR data shows requirement is met."""
    if not english_ok or not isinstance(parsed, dict):
        return parsed
    skills = parsed.get("skills_match")
    if isinstance(skills, dict):
        gaps = skills.get("gaps")
        if isinstance(gaps, list):
            skills["gaps"] = [g for g in gaps if not _ENGLISH_GAP_RE.search(str(g))]
    rec = parsed.get("recommendation")
    if isinstance(rec, str) and rec:
        sentences = re.split(r"(?<=[.!?])\s+", rec.strip())
        kept = [s for s in sentences if s and not _ENGLISH_GAP_RE.search(s)]
        if kept and len(kept) < len(sentences):
            parsed["recommendation"] = " ".join(kept)
    return parsed


def _term_in_posting(term: str, posting_hay: str) -> bool:
    t = (term or "").strip().lower()
    if not t or not posting_hay:
        return False
    if t in posting_hay:
        return True
    parts = [p for p in re.split(r"[\s/&+]+", t) if len(p) >= 3]
    return bool(parts) and all(p in posting_hay for p in parts)


_SPURIOUS_GAP_TOOLS = (
    "sap",
    "salesforce",
    "zapier",
    "power bi",
    "tableau",
    "hubspot",
    "kubernetes",
    "terraform",
)


def _scrub_recommendation_for_removed_gaps(
    parsed: dict,
    removed_terms: set[str],
    posting_hay: str,
) -> dict:
    rec = parsed.get("recommendation")
    if not isinstance(rec, str) or not rec.strip():
        return parsed
    sentences = re.split(r"(?<=[.!?])\s+", rec.strip())
    kept: list[str] = []
    for sentence in sentences:
        if not sentence:
            continue
        low = sentence.lower()
        drop = any(term in low for term in removed_terms)
        if not drop:
            for tool in _SPURIOUS_GAP_TOOLS:
                if tool in low and tool not in posting_hay:
                    drop = True
                    break
        if not drop:
            kept.append(sentence)
    if kept:
        parsed["recommendation"] = " ".join(kept)
    return parsed


def sanitize_posting_gaps(parsed: dict, job_text: str) -> dict:
    """Keep skills_match.gaps only for requirements explicitly named in the posting."""
    if not isinstance(parsed, dict):
        return parsed
    posting_hay = _normalize_job_posting_text(job_text).lower()
    skills = parsed.get("skills_match")
    removed: set[str] = set()
    if isinstance(skills, dict):
        gaps = skills.get("gaps")
        if isinstance(gaps, list):
            kept: list = []
            for gap in gaps:
                gs = str(gap).strip()
                if not gs:
                    continue
                if _term_in_posting(gs, posting_hay):
                    kept.append(gap)
                else:
                    removed.add(gs.lower())
            skills["gaps"] = kept
    return _scrub_recommendation_for_removed_gaps(parsed, removed, posting_hay)


def profile_excerpt_for_eval(profile_md: str, max_chars: int = PROFILE_MAX) -> str:
    parts = []
    for header in ("## Identity", "## Professional Experience", "## Technical Skills"):
        bit = _section_excerpt(profile_md, header, max_chars // 2)
        if bit:
            parts.append(bit)
    if not parts:
        return profile_md[:max_chars]
    out = "\n\n".join(parts)
    return out[:max_chars]


def framework_excerpt_for_eval(framework_md: str, max_chars: int = FRAMEWORK_MAX) -> str:
    if not framework_md:
        return ""
    lines = []
    for line in framework_md.splitlines():
        if "[YOUR_" in line or "[PLACEHOLDER]" in line:
            continue
        lines.append(line)
        if sum(len(x) + 1 for x in lines) > max_chars:
            break
    return "\n".join(lines)[:max_chars]


_JOB_SECTION_MARKERS = (
    "Your responsibilities",
    "Our requirements",
    "Requirements:",
    "Essential Qualifications",
    "Responsibilities:",
    "About the role",
    "About the job",
    "What you'll do",
    "What you will do",
    "Nice to have:",
    "Technologies we use",
    "Obowiązki",
    "Wymagania",
    "O projekcie",
    "Opis stanowiska",
)

_LINKEDIN_NOISE_MARKERS = (
    "LinkedIn szanuje",
    "cookie",
    "Zaakceptuj",
    "Zaloguj się",
)


def _excerpt_start_offset(text: str) -> int:
    """Skip LinkedIn cookie/login boilerplate at the start of raw_text."""
    head = text[:800].lower()
    if not any(n.lower() in head for n in _LINKEDIN_NOISE_MARKERS):
        return 0
    best = 0
    for marker in _JOB_SECTION_MARKERS:
        idx = text.find(marker)
        if idx >= 0 and (best == 0 or idx < best):
            best = idx
    for marker in (" IS HIRING", " IS HIRING!", "Show more"):
        idx = text.find(marker)
        if idx >= 0 and (best == 0 or idx < best):
            best = idx
    return best


def _normalize_job_posting_text(raw_text: str) -> str:
    text = html.unescape(raw_text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def job_posting_excerpt(raw_text: str, max_chars: int = JOB_POSTING_MAX) -> str:
    text = _normalize_job_posting_text(raw_text)
    start = _excerpt_start_offset(text)
    if start:
        text = text[start:].strip()
    sections: list[str] = []
    for marker in _JOB_SECTION_MARKERS:
        idx = text.find(marker)
        if idx < 0:
            continue
        chunk = text[idx : idx + max(180, max_chars // 3)].strip()
        if chunk and chunk not in sections:
            sections.append(chunk)
    if sections:
        text = "\n\n".join(sections)
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def profile_excerpt_for_cv(profile_md: str, max_chars: int = CV_PROFILE_MAX) -> str:
    parts = []
    for header in ("## Identity", "## Technical Skills"):
        bit = _section_excerpt(profile_md, header, max_chars // 2)
        if bit:
            parts.append(bit)
    if not parts:
        return profile_md[:max_chars]
    return "\n\n".join(parts)[:max_chars]


def experience_source_for_cv(
    experience_entries,
    max_chars: int = CV_EXPERIENCE_BATCH_MAX,
    *,
    max_bullets: int = 3,
) -> str:
    """Compact experience blocks for one LLM tailoring batch."""
    blocks: list[str] = []
    for e in experience_entries:
        loc = f" | {e.location}" if getattr(e, "location", "") else ""
        header = f"### {e.title} | {e.company}{loc} | {e.period}"
        bullets = getattr(e, "bullets", []) or []
        body = "\n".join(f"- {b[:220]}" for b in bullets[:max_bullets])
        blocks.append(f"{header}\n{body}".strip())
    text = "\n\n".join(blocks)
    if len(text) <= max_chars:
        return text
    trimmed: list[str] = []
    total = 0
    for block in blocks:
        if total + len(block) > max_chars:
            break
        trimmed.append(block)
        total += len(block) + 2
    return "\n\n".join(trimmed)


def master_summary_excerpt(master_text: str, max_chars: int = 400) -> str:
    if not master_text:
        return ""
    m = re.search(
        r"SUMMARY ATS\s*\n(.*?)(?:\nKLUCZOWE KOMPETENCJE|\n[A-ZĄĆĘŁŃÓŚŹŻ]{4,})",
        master_text,
        re.S,
    )
    if m:
        return m.group(1).strip()[:max_chars]
    return master_text[:max_chars]


def tex_excerpt_for_review(tex: str, max_chars: int = REVIEWER_TEX_MAX // 2) -> str:
    text = tex.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n% [… truncated …]"


def llm_failure_note(exc: Exception, llm_ok: bool, *, n_ctx: int = 2048) -> str:
    msg = str(exc).lower()
    if "context" in msg or "exceeds" in msg or "n_ctx" in msg:
        return (
            f"LLM — przekroczony limit kontekstu ({n_ctx} tokenów). "
            "Spróbuj ponownie; apply używa wielu krótkich passów dopasowania."
        )
    if not llm_ok:
        return "LLM niedostępny — uruchom Bielik i spróbuj ponownie."
    return f"LLM zwrócił błąd: {exc}"
