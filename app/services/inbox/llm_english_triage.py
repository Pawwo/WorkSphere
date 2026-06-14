"""Backward-compatible wrapper — use llm_language_triage."""

from __future__ import annotations

from app.services.inbox.llm_language_triage import (
    batch_extract_language_llm,
    extract_language_requirements_llm,
)


async def assess_english_requirement_llm(llm, posting: str):
    reqs = await extract_language_requirements_llm(llm, posting)
    for req in reqs:
        if req.language == "english":
            return True, req.token
    return False, None


async def batch_assess_english_llm(items, settings=None):
    extracts = await batch_extract_language_llm(items, settings)
    out = {}
    for key, reqs in extracts.items():
        for req in reqs:
            if req.language == "english":
                out[key] = (True, req.token)
                break
    return out
