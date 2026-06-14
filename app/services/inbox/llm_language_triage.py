"""LLM-based language requirement extraction for inbox triage."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional

from app.llm.client import BielikClient
from app.llm.structured import extract_json
from app.llm.token_budgets import LANGUAGE_TRIAGE
from app.models.setup import LanguageCode, LanguageLevel
from app.prompts.loader import render_prompt
from app.services.inbox.language_triage import LanguageRequirement
from app.services.profile.language_skills import normalize_language_code, normalize_level

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

_VALID_LEVELS = frozenset({"native", "C2", "C1", "B2", "B1", "A2", "A1"})
_MIN_LLM_TEXT = 80
_POSTING_MAX_CHARS = 2800

_FOREIGN_LANG_RE = re.compile(
    r"english|angielsk|german|niemiec|french|franc|spanish|hiszpan|"
    r"czech|czesk|dutch|holand|italian|włosk|wlosk|ukrainian|ukraiń",
    re.I,
)
_PL_ONLY_RE = re.compile(
    r"język polsk|jezyk polsk|język ojczysty|native polish|polski\s*(wymagany|B2|C1)?",
    re.I,
)


def posting_text_for_llm(text: str, *, max_chars: int = _POSTING_MAX_CHARS) -> str:
    return (text or "").strip()[:max_chars]


def likely_needs_language_llm(posting: str) -> bool:
    """Skip LLM when posting clearly has no foreign-language requirements."""
    text = (posting or "").strip()
    if len(text) < _MIN_LLM_TEXT:
        return False
    if _FOREIGN_LANG_RE.search(text):
        return True
    if _PL_ONLY_RE.search(text) and not _FOREIGN_LANG_RE.search(text):
        return False
    return True


def _parse_requirements(raw: object) -> list[LanguageRequirement]:
    if not isinstance(raw, list):
        if isinstance(raw, dict) and "requirements" in raw:
            raw = raw["requirements"]
        else:
            return []
    out: list[LanguageRequirement] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        lang = normalize_language_code(str(item.get("language") or ""))
        level = normalize_level(str(item.get("level") or ""))
        if not lang or not level or level not in _VALID_LEVELS:
            continue
        evidence = str(item.get("evidence") or "").strip()[:80] or None
        out.append(
            LanguageRequirement(
                language=lang,
                level=level,  # type: ignore[arg-type]
                token=f"{lang}_{level.lower()}",
                evidence=evidence,
            )
        )
    return out


async def extract_language_requirements_llm(
    llm: BielikClient,
    posting: str,
) -> list[LanguageRequirement]:
    if not likely_needs_language_llm(posting):
        return []
    text = posting_text_for_llm(posting)
    if len(text) < _MIN_LLM_TEXT:
        return []
    prompt = render_prompt("language_requirements.jinja2", posting=text)
    try:
        raw = await llm.chat_complete(
            [
                {
                    "role": "system",
                    "content": (
                        "Jesteś filtrem rekrutacyjnym. Odpowiadasz wyłącznie poprawnym JSON "
                        "(tablica wymagań językowych). Bez markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=LANGUAGE_TRIAGE,
            temperature=0.0,
        )
    except Exception as exc:
        logger.warning("LLM language triage failed: %s", exc)
        return []

    data = extract_json(raw)
    if isinstance(data, dict) and not isinstance(data.get("requirements"), list):
        for key in ("languages", "items", "result"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            if data.get("language") and data.get("level"):
                data = [data]
            elif data.get("skip") is False:
                return []
    return _parse_requirements(data)


async def batch_extract_language_llm(
    items: list[tuple[str, str]],
    settings: Optional[Settings] = None,
) -> dict[str, list[LanguageRequirement]]:
    """Map seen_jobs key -> extracted requirements (may be empty)."""
    if not items:
        return {}

    from app.config import get_settings

    settings = settings or get_settings()
    llm = BielikClient(settings)
    if not await llm.is_ready(probe=True):
        logger.info("LLM offline or probe failed — skipping language LLM triage for %s jobs", len(items))
        return {}

    sem = asyncio.Semaphore(max(1, settings.llm_concurrency))

    async def one(key: str, text: str) -> tuple[str, list[LanguageRequirement]]:
        async with sem:
            reqs = await extract_language_requirements_llm(llm, text)
            return key, reqs

    results = await asyncio.gather(*(one(key, text) for key, text in items))
    return {key: reqs for key, reqs in results if reqs}
