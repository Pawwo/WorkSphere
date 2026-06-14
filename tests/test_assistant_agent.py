"""Assistant agent loop with mocked LLM."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.services.assistant.agent_service import AgentService


def _settings(tmp_path: Path) -> Settings:
    return Settings().model_copy(update={"data_dir": tmp_path.resolve()})


@pytest.mark.asyncio
async def test_agent_answer_flow(tmp_path):
    settings = _settings(tmp_path)
    svc = AgentService(settings)
    answer_json = '{"type":"answer","content":"Masz 3 oferty w inbox."}'

    with patch.object(svc.llm, "chat_complete", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = answer_json
        with patch.object(svc, "_maybe_extract_memory", new_callable=AsyncMock):
            result = await svc.handle_message("Ile ofert mam?")

    assert result["ok"] is True
    assert "inbox" in result["content"].lower()
    messages = await svc.list_messages()
    assert len(messages) >= 2
    assert messages[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_agent_tool_then_answer(tmp_path):
    settings = _settings(tmp_path)
    svc = AgentService(settings)

    tool_json = '{"type":"tool_call","tool":"get_inbox_counts","args":{}}'
    answer_json = '{"type":"answer","content":"Podsumowanie gotowe."}'

    with patch.object(svc.llm, "chat_complete", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = [tool_json, answer_json]
        with patch.object(svc, "_maybe_extract_memory", new_callable=AsyncMock):
            result = await svc.handle_message("Pokaż statystyki")

    assert result["ok"] is True
    assert result.get("tool_runs")
    assert len(result["tool_runs"]) >= 1


@pytest.mark.asyncio
async def test_empty_message_rejected(tmp_path):
    settings = _settings(tmp_path)
    svc = AgentService(settings)
    result = await svc.handle_message("   ")
    assert result["ok"] is False
