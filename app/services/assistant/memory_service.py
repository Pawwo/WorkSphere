"""Assistant conversation and long-term memory storage."""

from __future__ import annotations

import json
from typing import Optional

from app.config import Settings, get_settings
from app.storage.db import Database

DEFAULT_THREAD_ID = "default"
CONTEXT_MESSAGE_LIMIT = 8

_CONTEXT_SKIP_MARKERS = (
    "Błąd LLM:",
    "LLM niedostępny",
    "Wystąpił błąd połączenia",
    "Sprawdź /tools",
    "Sprawdź ustawienia w /tools",
    "Nie udało się przetworzyć odpowiedzi",
    "Osiągnięto limit kroków agenta",
)


class MemoryService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.db = Database(self.settings.db_path)

    async def ensure_default_thread(self) -> str:
        await self.db.ensure_assistant_thread(DEFAULT_THREAD_ID)
        return DEFAULT_THREAD_ID

    async def list_messages(self, thread_id: str = DEFAULT_THREAD_ID, limit: int = 50) -> list[dict]:
        await self.db.ensure_assistant_thread(thread_id)
        return await self.db.list_assistant_messages(thread_id, limit=limit)

    async def add_message(
        self,
        thread_id: str,
        *,
        role: str,
        content: str,
        tool_calls: Optional[list | dict] = None,
    ) -> int:
        tool_json = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
        return await self.db.add_assistant_message(
            thread_id,
            role=role,
            content=content,
            tool_calls_json=tool_json,
        )

    async def get_context_messages(self, thread_id: str = DEFAULT_THREAD_ID) -> list[dict]:
        rows = await self.list_messages(thread_id, limit=50)
        cleaned: list[dict] = []
        for r in rows:
            content = r.get("content") or ""
            if not content:
                continue
            if r["role"] == "assistant" and any(m in content for m in _CONTEXT_SKIP_MARKERS):
                continue
            cleaned.append({"role": r["role"], "content": content})

        collapsed: list[dict] = []
        for msg in cleaned:
            if collapsed and collapsed[-1]["role"] == msg["role"]:
                collapsed[-1] = msg
            else:
                collapsed.append(msg)

        if collapsed and collapsed[0]["role"] == "assistant":
            collapsed = collapsed[1:]

        return collapsed[-CONTEXT_MESSAGE_LIMIT:]

    async def list_facts(self, limit: int = 100) -> list[dict]:
        return await self.db.list_assistant_memory(limit=limit)

    async def search_facts(self, query: str, limit: int = 20) -> list[dict]:
        if not query.strip():
            return await self.list_facts(limit=limit)
        return await self.db.search_assistant_memory(query, limit=limit)

    async def remember_fact(
        self,
        *,
        category: str,
        key: str,
        content: str,
        source_message_id: Optional[int] = None,
    ) -> dict:
        valid = {"preference", "workflow", "context"}
        cat = category if category in valid else "context"
        mid = await self.db.add_assistant_memory(
            category=cat,
            key=key[:200],
            content=content[:2000],
            source_message_id=source_message_id,
        )
        return {"id": mid, "category": cat, "key": key, "content": content}

    async def delete_fact(self, memory_id: int) -> bool:
        return await self.db.delete_assistant_memory(memory_id)

    async def count_facts(self) -> int:
        return await self.db.count_assistant_memory()

    def format_facts_for_prompt(self, facts: list[dict]) -> str:
        if not facts:
            return "(brak zapisanych faktów)"
        lines = []
        for f in facts[:30]:
            lines.append(f"- [{f.get('category', 'context')}] {f.get('key', '')}: {f.get('content', '')}")
        return "\n".join(lines)

    async def log_tool_run(
        self,
        thread_id: str,
        *,
        tool_name: str,
        args: dict,
        result: dict | str | None = None,
        status: str = "ok",
    ) -> int:
        result_json = json.dumps(result, ensure_ascii=False, default=str) if result is not None else None
        return await self.db.add_assistant_tool_run(
            thread_id,
            tool_name=tool_name,
            args_json=json.dumps(args, ensure_ascii=False),
            result_json=result_json,
            status=status,
        )
