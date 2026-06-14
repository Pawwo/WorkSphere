"""Backward-compat tests for llm_english_triage wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.inbox.llm_english_triage import (
    assess_english_requirement_llm,
    batch_assess_english_llm,
)


@pytest.mark.asyncio
async def test_assess_english_requirement_llm_parses_skip():
    llm = AsyncMock()
    llm.chat_complete = AsyncMock(
        return_value='[{"language": "english", "level": "C1", "evidence": "Angielski C1"}]'
    )
    skip, token = await assess_english_requirement_llm(
        llm,
        "Qualifications: Very good English skills (minimum C1). " * 3,
    )
    assert skip is True
    assert token is not None


@pytest.mark.asyncio
async def test_assess_english_requirement_llm_rejects_empty():
    llm = AsyncMock()
    llm.chat_complete = AsyncMock(return_value="[]")
    skip, token = await assess_english_requirement_llm(
        llm,
        "English B2 level required for this role. " * 5,
    )
    assert skip is False
    assert token is None


@pytest.mark.asyncio
async def test_batch_assess_english_llm_skips_when_llm_offline():
    with patch(
        "app.services.inbox.llm_language_triage.BielikClient"
    ) as client_cls:
        client_cls.return_value.is_ready = AsyncMock(return_value=False)
        result = await batch_assess_english_llm([("k1", "Fluent English required. " * 10)])
    assert result == {}
