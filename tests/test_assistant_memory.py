"""Assistant memory service."""

from pathlib import Path

import pytest

from app.config import Settings
from app.services.assistant.memory_service import DEFAULT_THREAD_ID, MemoryService


def _settings(tmp_path: Path) -> Settings:
    return Settings().model_copy(update={"data_dir": tmp_path.resolve()})


@pytest.mark.asyncio
async def test_default_thread_and_messages(tmp_path):
    settings = _settings(tmp_path)
    mem = MemoryService(settings)
    thread_id = await mem.ensure_default_thread()
    assert thread_id == DEFAULT_THREAD_ID
    mid = await mem.add_message(thread_id, role="user", content="Cześć")
    assert mid > 0
    rows = await mem.list_messages(thread_id)
    assert len(rows) == 1
    assert rows[0]["content"] == "Cześć"


@pytest.mark.asyncio
async def test_remember_and_delete_fact(tmp_path):
    settings = _settings(tmp_path)
    mem = MemoryService(settings)
    fact = await mem.remember_fact(
        category="preference",
        key="język",
        content="Preferuję oferty po polsku",
    )
    assert fact["id"] > 0
    facts = await mem.list_facts()
    assert len(facts) == 1
    found = await mem.search_facts("polsku")
    assert len(found) == 1
    ok = await mem.delete_fact(fact["id"])
    assert ok is True
    assert await mem.count_facts() == 0


@pytest.mark.asyncio
async def test_context_collapses_consecutive_user_messages(tmp_path):
    settings = _settings(tmp_path)
    mem = MemoryService(settings)
    thread_id = await mem.ensure_default_thread()
    await mem.add_message(thread_id, role="user", content="co?")
    await mem.add_message(thread_id, role="user", content="CO?")
    await mem.add_message(thread_id, role="assistant", content="Błąd LLM: offline")
    await mem.add_message(thread_id, role="user", content="Ile ofert?")
    ctx = await mem.get_context_messages(thread_id)
    assert len(ctx) == 1
    assert ctx[0]["role"] == "user"
    assert ctx[0]["content"] == "Ile ofert?"


@pytest.mark.asyncio
async def test_context_messages_limit(tmp_path):
    settings = _settings(tmp_path)
    mem = MemoryService(settings)
    thread_id = await mem.ensure_default_thread()
    for i in range(25):
        await mem.add_message(thread_id, role="user", content=f"msg {i}")
    ctx = await mem.get_context_messages(thread_id)
    assert len(ctx) <= 8
