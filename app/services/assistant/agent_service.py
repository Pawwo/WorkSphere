"""Assistant agent loop — LLM + tool registry + memory."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.llm.exceptions import LlmDegradedError
from app.llm.structured import extract_json
from app.llm.token_budgets import ASSISTANT, ASSISTANT_MEMORY_EXTRACT
from app.prompts.loader import render_prompt
from app.services.assistant.context_builder import ContextBuilder
from app.services.assistant.memory_service import DEFAULT_THREAD_ID, MemoryService
from app.services.assistant.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5

_LLM_ERROR_REPLY = re.compile(
    r"błąd połączenia|connection attempts failed|sprawdź konfiguracj|check.*config",
    re.I,
)


class AgentService:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.memory = MemoryService(self.settings)
        self.tools = ToolRegistry(self.settings, memory_service=self.memory)
        self.context = ContextBuilder(self.settings)
        self.llm = BielikClient(self.settings)

    async def status(self) -> dict:
        thread_id = await self.memory.ensure_default_thread()
        health = await self.llm.healthcheck_extended()
        return {
            "thread_id": thread_id,
            "llm_ok": health.get("ok", False),
            "llm_model": self.llm.model,
            "memory_facts_count": await self.memory.count_facts(),
            "health": health,
        }

    async def list_messages(self, thread_id: str = DEFAULT_THREAD_ID) -> list[dict]:
        await self.memory.ensure_default_thread()
        rows = await self.memory.list_messages(thread_id)
        return [
            {
                "id": r["id"],
                "role": r["role"],
                "content": r["content"],
                "tool_calls": json.loads(r["tool_calls_json"]) if r.get("tool_calls_json") else None,
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    async def handle_message(
        self,
        content: str,
        *,
        thread_id: str = DEFAULT_THREAD_ID,
        confirm_action_id: Optional[int] = None,
    ) -> dict:
        await self.memory.ensure_default_thread()
        thread_id = thread_id or DEFAULT_THREAD_ID

        if confirm_action_id:
            return await self._handle_confirm(thread_id, confirm_action_id, content)

        if not content.strip():
            return {"ok": False, "error": "Pusta wiadomość"}

        await self.memory.add_message(thread_id, role="user", content=content.strip())

        ready = await self._ensure_llm_ready()
        if not ready.get("ok"):
            return self._llm_unavailable_response(ready)

        response = await self._run_agent_loop(thread_id)
        if response.get("ok", True) and response.get("content"):
            msg_id = await self.memory.add_message(
                thread_id, role="assistant", content=response["content"]
            )
            response["message_id"] = msg_id
            await self._maybe_extract_memory(content, response["content"], msg_id)
        return response

    async def _ensure_llm_ready(self) -> dict:
        health = await self.llm.healthcheck_extended(force_probe=True)
        return {"ok": health.get("ok", False), "health": health}

    def _llm_unavailable_response(self, ready: dict) -> dict:
        detail = ready.get("error") or ready.get("status") or "niedostępny"
        return {
            "ok": False,
            "type": "error",
            "content": (
                f"LLM niedostępny ({detail}). "
                "Wejdź w Narzędzia, ustaw LLM_BASE_URL i kliknij „Test połączenia”."
            ),
        }

    async def _handle_confirm(
        self, thread_id: str, action_id: int, content: str
    ) -> dict:
        run = await self.memory.db.get_assistant_tool_run(action_id)
        if not run or run.get("status") != "pending":
            return {"ok": False, "error": "Nieprawidłowa lub wygasła akcja do potwierdzenia"}
        args = json.loads(run.get("args_json") or "{}")
        tool_name = run.get("tool_name", "")
        result = await self.tools.execute(tool_name, args, confirmed=True)
        status = "ok" if result.get("ok") else "failed"
        await self.memory.db.update_assistant_tool_run(
            action_id,
            result_json=json.dumps(result, ensure_ascii=False, default=str),
            status=status,
        )
        summary = self._format_tool_result(tool_name, result)
        await self.memory.add_message(thread_id, role="user", content=f"[Potwierdzono] {content}")
        msg_id = await self.memory.add_message(thread_id, role="assistant", content=summary)
        return {
            "ok": True,
            "type": "answer",
            "content": summary,
            "message_id": msg_id,
            "tool_runs": [{"tool": tool_name, "result": result}],
            "confirmed_action_id": action_id,
        }

    async def _run_agent_loop(self, thread_id: str) -> dict:
        facts = await self.memory.list_facts(limit=10)
        system_prompt = render_prompt(
            "assistant_system.jinja2",
            system_snapshot=json.dumps(self.context.snapshot(), ensure_ascii=False),
            memory_facts=self.memory.format_facts_for_prompt(facts),
            tool_names=self.tools.compact_tool_specs_text(),
        )
        history = await self.memory.get_context_messages(thread_id)
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})

        tool_runs: list[dict] = []
        pending_confirm: Optional[dict] = None

        for _ in range(MAX_ITERATIONS):
            try:
                raw = await self.llm.chat_complete(messages, max_tokens=ASSISTANT, temperature=0.1)
            except LlmDegradedError as exc:
                return {
                    "ok": False,
                    "type": "error",
                    "content": (
                        f"LLM zwrócił błędną odpowiedź ({exc}). "
                        "Spróbuj ponownie po „Test połączenia” w /tools."
                    ),
                }
            except Exception as exc:
                logger.exception("assistant LLM error")
                err = str(exc).lower()
                if "connection" in err or "connect" in err:
                    return self._llm_unavailable_response({"ok": False, "error": exc})
                return {
                    "ok": False,
                    "type": "error",
                    "content": f"Błąd LLM: {exc}. Sprawdź /tools.",
                }

            parsed = extract_json(raw)
            if not isinstance(parsed, dict):
                text = raw.strip() or ""
                if _LLM_ERROR_REPLY.search(text):
                    return self._llm_unavailable_response({"ok": False, "error": text[:200]})
                return {
                    "ok": True,
                    "type": "answer",
                    "content": text or "Nie udało się przetworzyć odpowiedzi — spróbuj ponownie.",
                    "tool_runs": tool_runs,
                }

            msg_type = parsed.get("type")
            if msg_type == "answer":
                answer = str(parsed.get("content") or "").strip()
                if _LLM_ERROR_REPLY.search(answer):
                    return self._llm_unavailable_response({"ok": False, "error": answer[:200]})
                return {
                    "ok": True,
                    "type": "answer",
                    "content": answer or "OK.",
                    "tool_runs": tool_runs,
                    "pending_confirm": pending_confirm,
                }

            if msg_type == "tool_call":
                tool_name = str(parsed.get("tool") or "")
                args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
                result = await self.tools.execute(tool_name, args, confirmed=False)
                run_id = await self.memory.log_tool_run(
                    thread_id,
                    tool_name=tool_name,
                    args=args,
                    result=result,
                    status="pending" if result.get("needs_confirm") else ("ok" if result.get("ok") else "failed"),
                )
                tool_runs.append({"id": run_id, "tool": tool_name, "args": args, "result": result})

                if result.get("needs_confirm"):
                    pending_confirm = {
                        "confirm_action_id": run_id,
                        "tool": tool_name,
                        "args": args,
                        "message": result.get("message", "Potwierdź akcję"),
                    }
                    confirm_text = (
                        f"{result.get('message', 'Potwierdź akcję')} "
                        f"(narzędzie: {tool_name}). Kliknij Potwierdź, aby kontynuować."
                    )
                    return {
                        "ok": True,
                        "type": "answer",
                        "content": confirm_text,
                        "tool_runs": tool_runs,
                        "pending_confirm": pending_confirm,
                    }

                tool_msg = self._format_tool_result(tool_name, result)
                messages.append({"role": "assistant", "content": json.dumps(parsed, ensure_ascii=False)})
                messages.append({"role": "user", "content": f"[Wynik narzędzia {tool_name}]: {tool_msg}"})
                continue

            if _LLM_ERROR_REPLY.search(raw):
                return self._llm_unavailable_response({"ok": False, "error": raw[:200]})
            return {
                "ok": True,
                "type": "answer",
                "content": raw.strip(),
                "tool_runs": tool_runs,
            }

        return {
            "ok": True,
            "type": "answer",
            "content": "Osiągnięto limit kroków agenta. Spróbuj uprościć pytanie.",
            "tool_runs": tool_runs,
        }

    def _format_tool_result(self, tool_name: str, result: dict) -> str:
        if not result.get("ok"):
            return f"Błąd {tool_name}: {result.get('error', result)}"
        inner = result.get("result")
        try:
            return json.dumps(inner, ensure_ascii=False, default=str)[:3000]
        except TypeError:
            return str(inner)[:3000]

    async def _maybe_extract_memory(
        self, user_message: str, assistant_message: str, source_message_id: int
    ) -> None:
        prompt = render_prompt(
            "assistant_memory_extract.jinja2",
            user_message=user_message[:500],
            assistant_message=assistant_message[:500],
        )
        try:
            raw = await self.llm.chat_complete(
                [{"role": "user", "content": prompt}],
                max_tokens=ASSISTANT_MEMORY_EXTRACT,
                temperature=0.0,
                _skip_esc_guard=True,
            )
            parsed = extract_json(raw)
            if not isinstance(parsed, dict):
                return
            for fact in parsed.get("facts") or []:
                if not isinstance(fact, dict):
                    continue
                key = str(fact.get("key") or "").strip()
                content = str(fact.get("content") or "").strip()
                if not key or not content:
                    continue
                await self.memory.remember_fact(
                    category=str(fact.get("category") or "context"),
                    key=key,
                    content=content,
                    source_message_id=source_message_id,
                )
        except Exception as exc:
            logger.debug("memory extract skipped: %s", exc)
