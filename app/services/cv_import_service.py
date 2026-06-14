"""CV import — condense long CVs, multi-pass LLM extract, career inference."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.llm.client import BielikClient
from app.llm.structured import extract_json
from app.llm.token_budgets import CV_CAREER, CV_EXTRACT, CV_EXTRACT_EXPERIENCE, CV_EXTRACT_SKILLS
from app.models.setup import _split_period
from app.prompts.loader import render_prompt

logger = logging.getLogger(__name__)

# llama.cpp n_ctx=4096 — keep each pass input bounded for local GPU Vulkan
MAX_HEADER_CHARS = 1400
MAX_EXPERIENCE_PASS_CHARS = 2800
MAX_SKILLS_CHARS = 1000

_JOB_HEADER = re.compile(
    r"^(.+?\|.+\|.+?\d{2}[\./]\d{4}.+)$",
    re.MULTILINE | re.IGNORECASE,
)
_SECTION_MARKERS = (
    "DANE IDENTYFIKACYJNE",
    "DOŚWIADCZENIE ZAWODOWE",
    "WYKSZTAŁCENIE",
    "CERTYFIKATY",
    "JĘZYKI",
    "WYRÓŻNIENIA",
    "KLUCZOWE KOMPETENCJE",
    "UMIEJĘTNOŚCI",
    "NARZĘDZIA",
    "PUBLIKACJE",
)


def _section_slice(text: str, start: str, *ends: str) -> str:
    """Extract text between start marker and first end marker (or EOF)."""
    low = text.lower()
    s_key = start.lower()
    pos = low.find(s_key)
    if pos < 0:
        return ""
    pos += len(start)
    end_pos = len(text)
    for end in ends:
        e = low.find(end.lower(), pos)
        if e >= 0:
            end_pos = min(end_pos, e)
    return text[pos:end_pos].strip()


def _identity_snippet(text: str, limit: int = 1200) -> str:
    head = text[: min(len(text), 3500)]
    lines: list[str] = []
    for line in head.splitlines():
        s = line.strip()
        if not s:
            continue
        low = s.lower()
        if any(
            k in low
            for k in (
                "imię",
                "nazwisko",
                "lokalizacja",
                "telefon",
                "e-mail",
                "email",
                "linkedin",
                "github",
                "status",
                "język",
                "ogranicz",
                "hybryd",
                "zdaln",
                "@",
                "+48",
                "http",
            )
        ):
            lines.append(s)
    if not lines:
        lines = [ln.strip() for ln in head.splitlines()[:25] if ln.strip()]
    out = "\n".join(lines)
    return out[:limit]


def _job_blocks(experience_text: str, bullets_per_job: int = 4) -> list[str]:
    """Split experience section into job header + limited bullets."""
    lines = experience_text.splitlines()
    blocks: list[str] = []
    current: list[str] = []

    def flush():
        if current:
            blocks.append("\n".join(current))

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _JOB_HEADER.match(stripped) and current:
            flush()
            current = [stripped]
        elif _JOB_HEADER.match(stripped):
            current = [stripped]
        elif current:
            if stripped.startswith(("-", "•", "–")) or "Udokumentowane" in stripped:
                bullet_count = sum(1 for x in current if x.strip().startswith(("-", "•", "–")))
                if bullet_count < bullets_per_job:
                    current.append(stripped)
            elif "Słowa kluczowe ATS" in stripped:
                flush()
                current = []
    flush()
    return blocks


def _list_items(block: str, max_items: int = 25) -> list[str]:
    items = []
    for line in block.splitlines():
        s = line.strip().lstrip("-•–").strip()
        if s and len(s) > 2 and not s.endswith(":"):
            items.append(s)
        if len(items) >= max_items:
            break
    return items


def _experience_raw(text: str) -> str:
    exp = _section_slice(
        text,
        "DOŚWIADCZENIE ZAWODOWE",
        "WYBRANE OSIĄGNIĘCIA",
        "DOŚWIADCZENIE EKSPERCKIE",
        "WYKSZTAŁCENIE",
        "ATS KEYWORDS",
    )
    if exp:
        return exp
    return "\n".join(m.group(1) for m in _JOB_HEADER.finditer(text))


def header_excerpt(cv_text: str, max_chars: int = MAX_HEADER_CHARS) -> str:
    """Identity, education, certs, languages, awards — no experience."""
    text = cv_text.replace("\r\n", "\n").strip()
    parts: list[str] = []
    ident = _identity_snippet(text, limit=500)
    if ident:
        parts.append("=== TOŻSAMOŚĆ ===\n" + ident)

    edu = _section_slice(text, "WYKSZTAŁCENIE", "CERTYFIKATY", "JĘZYKI", "WYRÓŻNIENIA")
    if not edu:
        edu_m = re.search(r"(Licencjat|Magister|Inżynier|MBA).{0,180}", text, re.I | re.DOTALL)
        if edu_m:
            edu = edu_m.group(0)
    if edu:
        parts.append("=== WYKSZTAŁCENIE ===\n" + edu[:350])

    certs = _section_slice(text, "CERTYFIKATY", "JĘZYKI", "WYRÓŻNIENIA", "UMIEJĘTNOŚCI")
    if certs:
        parts.append("=== CERTYFIKATY ===\n" + "\n".join(_list_items(certs, 10)))

    langs = _section_slice(text, "JĘZYKI", "WYRÓŻNIENIA", "CERTYFIKATY")
    if langs:
        parts.append("=== JĘZYKI ===\n" + langs[:200])

    awards = _section_slice(text, "WYRÓŻNIENIA", "DZIAŁALNOŚĆ", "ATS KEYWORDS")
    if awards:
        parts.append("=== NAGRODY ===\n" + "\n".join(_list_items(awards, 5)))

    pubs = _section_slice(text, "PUBLIKACJE", "DEBATY", "OBSZARY BIZNESOWE")
    if pubs:
        parts.append("=== PUBLIKACJE ===\n" + pubs[:250])

    out = "\n\n".join(parts)
    if len(out) < 80:
        out = text[:max_chars]
    return out[:max_chars]


def skills_excerpt(cv_text: str, max_chars: int = MAX_SKILLS_CHARS) -> str:
    text = cv_text.replace("\r\n", "\n").strip()
    parts: list[str] = []
    skills = _section_slice(
        text, "KLUCZOWE KOMPETENCJE", "OBSZARY SPECJALIZACJI", "DOŚWIADCZENIE ZAWODOWE"
    )
    if not skills:
        skills = _section_slice(text, "UMIEJĘTNOŚCI", "WYKSZTAŁCENIE", "CERTYFIKATY")
    if skills:
        parts.append("\n".join(_list_items(skills, 25)))
    tools = _section_slice(text, "NARZĘDZIA", "UMIEJĘTNOŚCI", "WYKSZTAŁCENIE")
    if tools:
        parts.append("NARZĘDZIA:\n" + "\n".join(_list_items(tools, 15)))
    out = "\n\n".join(parts) or text[:max_chars]
    return out[:max_chars]


def condense_cv(cv_text: str, max_chars: int = 3000) -> str:
    """Full condensed CV for career inference (not for single LLM extract pass)."""
    text = cv_text.replace("\r\n", "\n").strip()
    if len(text) <= max_chars:
        return text
    parts = [
        header_excerpt(text, 1200),
        "=== DOŚWIADCZENIE ===\n" + experience_only_excerpt(text, 1200),
        "=== UMIEJĘTNOŚCI ===\n" + skills_excerpt(text, 600),
    ]
    return "\n\n".join(parts)[:max_chars]


def experience_only_excerpt(cv_text: str, max_chars: int = MAX_EXPERIENCE_PASS_CHARS) -> str:
    """Job title lines only — fits small LLM context."""
    exp_raw = _experience_raw(cv_text)
    if not exp_raw:
        return ""
    headers = [b.split("\n")[0] for b in _job_blocks(exp_raw, bullets_per_job=0)]
    if headers:
        return "\n".join(headers)[:max_chars]
    return exp_raw[:max_chars]


def parse_job_lines_from_excerpt(exp_text: str) -> list[dict]:
    """Deterministic fallback — parse `Title | Company | Loc | dates` lines."""
    entries: list[dict] = []
    for line in exp_text.splitlines():
        stripped = line.strip()
        if not stripped or "|" not in stripped:
            continue
        if not re.search(r"\d{2}[\./]\d{4}", stripped):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        if len(parts) < 2:
            continue
        title = parts[0]
        company = parts[1] if len(parts) > 1 else "—"
        location = parts[2] if len(parts) > 3 else (parts[2] if len(parts) == 3 and not re.search(r"\d{4}", parts[2]) else "")
        period = parts[-1] if re.search(r"\d{4}", parts[-1]) else (parts[3] if len(parts) > 3 else "")
        start, end = _split_period(period) if period else ("?", "present")
        entries.append(
            {
                "title": title,
                "company": company,
                "start": start,
                "end": end,
                "location": location or None,
                "bullets": [],
            }
        )
    return entries


def count_job_headers(cv_text: str) -> int:
    exp_raw = _experience_raw(cv_text)
    if exp_raw:
        return len(_job_blocks(exp_raw, bullets_per_job=0))
    return len(_JOB_HEADER.findall(cv_text))


def _merge_extract(base: dict, extra: dict) -> dict:
    out = {**base}
    for key, val in extra.items():
        if key == "identity" and isinstance(val, dict):
            out.setdefault("identity", {})
            out["identity"].update({k: v for k, v in val.items() if v})
        elif key == "skills" and isinstance(val, dict):
            out.setdefault("skills", {})
            out["skills"].update({k: v for k, v in val.items() if v})
        elif isinstance(val, list) and val:
            existing = out.get(key, [])
            seen = {str(x) for x in existing}
            for item in val:
                sig = str(item)
                if sig not in seen:
                    existing.append(item)
                    seen.add(sig)
            out[key] = existing
        elif val and not out.get(key):
            out[key] = val
    return out


class CvImportService:
    def __init__(self, llm: BielikClient | None = None):
        self.llm = llm or BielikClient()

    async def _llm_json(self, template: str, max_tokens: int = CV_EXTRACT, **ctx: Any) -> dict:
        prompt = render_prompt(template, **ctx)
        raw = await self.llm.chat_complete(
            [
                {"role": "system", "content": "Jesteś parserem CV. Zwracasz tylko JSON."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.0,
        )
        parsed = extract_json(raw)
        return parsed if isinstance(parsed, dict) else {}

    async def extract_from_cv(self, cv_text: str) -> tuple[dict, list[str]]:
        """Multi-pass extract (header / experience / skills); fits n_ctx=2048."""
        warnings: list[str] = []
        extracted: dict = {}

        header = header_excerpt(cv_text)
        logger.info("CV header excerpt %d chars", len(header))
        try:
            extracted = _merge_extract(
                extracted,
                await self._llm_json("cv_extract.jinja2", max_tokens=CV_EXTRACT, cv_text=header),
            )
        except Exception as exc:
            logger.warning("CV header extract failed: %s", exc)
            warnings.append(f"Nagłówek CV: {exc}")

        exp_text = experience_only_excerpt(cv_text)
        logger.info("CV experience excerpt %d chars", len(exp_text))
        fallback_jobs = parse_job_lines_from_excerpt(exp_text)
        llm_jobs: list[dict] = []
        try:
            exp_part = await self._llm_json(
                "cv_extract_experience.jinja2", max_tokens=CV_EXTRACT_EXPERIENCE, cv_text=exp_text
            )
            llm_jobs = [
                j
                for j in (exp_part.get("experience") or [])
                if j.get("title") and j.get("company")
            ]
        except Exception as exc:
            logger.warning("CV experience extract failed: %s", exc)
            warnings.append(f"Doświadczenie (LLM): {exc}")

        if fallback_jobs and len(fallback_jobs) >= len(llm_jobs):
            extracted["experience"] = fallback_jobs
            if llm_jobs:
                warnings.append(
                    f"Doświadczenie: {len(fallback_jobs)} stanowisk (parser), "
                    "bullets uzupełnij ręcznie w sekcji 3"
                )
        elif llm_jobs:
            extracted = _merge_extract(extracted, {"experience": llm_jobs})
        elif fallback_jobs:
            extracted["experience"] = fallback_jobs

        skills_text = skills_excerpt(cv_text)
        try:
            skills_part = await self._llm_json(
                "cv_extract_skills.jinja2", max_tokens=CV_EXTRACT_SKILLS, cv_text=skills_text
            )
            if skills_part.get("skills"):
                extracted = _merge_extract(extracted, skills_part)
        except Exception as exc:
            logger.warning("CV skills extract failed: %s", exc)
            warnings.append(f"Umiejętności: {exc}")

        expected_jobs = count_job_headers(cv_text)
        got_jobs = len(extracted.get("experience") or [])
        if expected_jobs > got_jobs + 1:
            warnings.append(
                f"W CV ~{expected_jobs} stanowisk, w profilu {got_jobs} — uzupełnij sekcję 3"
            )

        return extracted, warnings

    async def infer_career_and_search(self, extracted: dict, cv_text: str) -> dict:
        """Infer wizard sections 7 and 9 from extracted profile."""
        identity = extracted.get("identity") or {}
        roles = [e.get("title", "") for e in (extracted.get("experience") or [])[:6]]
        skills = extracted.get("skills") or {}
        snippet = condense_cv(cv_text, max_chars=2000)
        try:
            return await self._llm_json(
                "cv_career_infer.jinja2",
                max_tokens=CV_CAREER,
                full_name=identity.get("full_name", ""),
                location=identity.get("location", ""),
                roles=roles,
                programming=skills.get("programming", ""),
                domain=skills.get("domain", ""),
                tools=skills.get("tools", ""),
                cv_snippet=snippet[:1500],
            )
        except Exception as exc:
            logger.warning("Career infer failed: %s", exc)
            return {}
