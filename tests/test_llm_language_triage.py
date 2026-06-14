"""Tests for LLM language requirement triage."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.inbox.llm_language_triage import (
    batch_extract_language_llm,
    extract_language_requirements_llm,
)


@pytest.mark.asyncio
async def test_extract_language_requirements_llm_parses_array():
    llm = AsyncMock()
    llm.chat_complete = AsyncMock(
        return_value='[{"language": "english", "level": "C1", "evidence": "minimum C1"}]'
    )
    reqs = await extract_language_requirements_llm(
        llm,
        "Qualifications: Very good English skills (minimum C1). " * 3,
    )
    assert len(reqs) == 1
    assert reqs[0].language == "english"
    assert reqs[0].level == "C1"


@pytest.mark.asyncio
async def test_extract_language_requirements_llm_empty_b2():
    llm = AsyncMock()
    llm.chat_complete = AsyncMock(return_value="[]")
    reqs = await extract_language_requirements_llm(
        llm,
        "English B2 level required for this role. " * 5,
    )
    assert reqs == []


@pytest.mark.asyncio
async def test_batch_extract_language_llm_skips_when_llm_offline():
    with patch("app.services.inbox.llm_language_triage.BielikClient") as client_cls:
        client_cls.return_value.is_ready = AsyncMock(return_value=False)
        result = await batch_extract_language_llm([("k1", "Fluent English required. " * 10)])
    assert result == {}
