"""Whitelist of assistant tools — no code or filesystem access outside data services."""

from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any, Callable, Optional

from app.config import Settings, get_settings
from app.llm.client import BielikClient
from app.models.apply import ApplyRequest
from app.models.applications import ApplyAsyncRequest
from app.models.jobs import ManualSkipReasonItem, ScrapeRequest, SeenJobUpdate, SkipReasonDetails
from app.models.workflow import ExpandApplyRequest, ResetExecuteRequest
from app.models.pipeline import HIRING_STAGES as _HIRING_STAGES_LIST
from app.services.application_service import ApplicationService
from app.services.dashboard_service import DashboardService
from app.services.expand_service import ExpandService
from app.services.inbox_service import InboxService
from app.services.pipeline_service import PipelineService
from app.services.profile_service import ProfileService
from app.services.reset_service import ResetService
from app.services.scrape_service import ScrapeService
from app.services.task_service import TaskService

BLOCKED_TOOL_NAMES = frozenset(
    {
        "write_file",
        "edit_code",
        "run_shell",
        "run_subprocess",
        "update_llm_settings",
        "git",
        "pip",
    }
)

CONFIRM_REQUIRED_TOOLS = frozenset(
    {
        "start_full_apply",
        "reset_data",
        "expand_apply_profile",
    }
)

HIRING_STAGES = frozenset(_HIRING_STAGES_LIST)
_HIRING_STAGE_ENUM = "|".join(_HIRING_STAGES_LIST)


class ToolRegistry:
    def __init__(self, settings: Optional[Settings] = None, memory_service: Any = None):
        self.settings = settings or get_settings()
        self.memory = memory_service
        self._handlers: dict[str, Callable] = {
            "get_health": self._get_health,
            "get_inbox_counts": self._get_inbox_counts,
            "list_inbox_jobs": self._list_inbox_jobs,
            "list_applications": self._list_applications,
            "get_application": self._get_application,
            "get_setup_state": self._get_setup_state,
            "get_dashboard": self._get_dashboard,
            "search_memory": self._search_memory,
            "skip_inbox_job": self._skip_inbox_job,
            "evaluate_job": self._evaluate_job,
            "run_triage_async": self._run_triage_async,
            "start_scrape_async": self._start_scrape_async,
            "update_hiring_stage": self._update_hiring_stage,
            "add_application_note": self._add_application_note,
            "remember_fact": self._remember_fact,
            "start_full_apply": self._start_full_apply,
            "reset_data": self._reset_data,
            "expand_apply_profile": self._expand_apply_profile,
        }

    @property
    def tool_specs(self) -> list[dict]:
        return [
            {"name": "get_health", "description": "Status LLM, SearXNG i scraperów", "args": {}},
            {
                "name": "get_inbox_counts",
                "description": "Liczby ofert w inbox (tiery, statusy, fit)",
                "args": {},
            },
            {
                "name": "list_inbox_jobs",
                "description": "Lista ofert z inbox",
                "args": {
                    "tier": "priority|review|skip|evaluate (opcjonalnie)",
                    "status": "new|skipped|evaluated (opcjonalnie)",
                    "fit": "high|medium|low (opcjonalnie)",
                    "q": "fraza wyszukiwania (opcjonalnie)",
                    "limit": "max wyników (domyślnie 10)",
                },
            },
            {
                "name": "list_applications",
                "description": "Lista aplikacji w trackerze",
                "args": {
                    "hiring_stage": _HIRING_STAGE_ENUM,
                    "limit": "max wyników (domyślnie 20)",
                },
            },
            {
                "name": "get_application",
                "description": "Szczegóły aplikacji po ID",
                "args": {"application_id": "liczba całkowita"},
            },
            {
                "name": "get_setup_state",
                "description": "Status profilu i kreatora setup",
                "args": {},
            },
            {"name": "get_dashboard", "description": "Podsumowanie systemu", "args": {}},
            {
                "name": "search_memory",
                "description": "Przeszukaj zapamiętane fakty",
                "args": {"query": "fraza"},
            },
            {
                "name": "skip_inbox_job",
                "description": "Pomiń ofertę w inbox (tylko status=new)",
                "args": {"url": "URL oferty", "reason": "powód pominięcia"},
            },
            {
                "name": "evaluate_job",
                "description": "Rozpocznij ocenę oferty (parse+evaluate, bez CV)",
                "args": {"url": "URL oferty"},
            },
            {
                "name": "run_triage_async",
                "description": "Uruchom triage inbox w tle",
                "args": {},
            },
            {
                "name": "start_scrape_async",
                "description": "Uruchom scraping ofert w tle",
                "args": {
                    "query": "zapytanie (opcjonalnie)",
                    "broad": "true/false (opcjonalnie)",
                },
            },
            {
                "name": "update_hiring_stage",
                "description": "Zmień etap rekrutacji aplikacji",
                "args": {
                    "application_id": "ID aplikacji",
                    "hiring_stage": _HIRING_STAGE_ENUM,
                },
            },
            {
                "name": "add_application_note",
                "description": "Dodaj notatkę do aplikacji",
                "args": {"application_id": "ID", "body": "treść notatki"},
            },
            {
                "name": "remember_fact",
                "description": "Zapisz fakt do pamięci długoterminowej",
                "args": {
                    "category": "preference|workflow|context",
                    "key": "krótki klucz",
                    "content": "treść faktu",
                },
            },
            {
                "name": "start_full_apply",
                "description": "Pełny pipeline apply z CV (wymaga potwierdzenia)",
                "args": {"url": "URL oferty"},
                "requires_confirm": True,
            },
            {
                "name": "reset_data",
                "description": "Reset danych profilu (wymaga potwierdzenia tokenu RESET)",
                "args": {"confirm_token": "musi być RESET"},
                "requires_confirm": True,
            },
            {
                "name": "expand_apply_profile",
                "description": "Zastosuj rozszerzenie kompetencji profilu (wymaga potwierdzenia)",
                "args": {},
                "requires_confirm": True,
            },
        ]

    def compact_tool_specs_text(self) -> str:
        parts = []
        for spec in self.tool_specs:
            args = spec.get("args") or {}
            if args:
                arg_keys = ",".join(args.keys())
                parts.append(f"{spec['name']}({arg_keys})")
            else:
                parts.append(spec["name"])
        return ", ".join(parts)

    def is_allowed(self, name: str) -> bool:
        return name in self._handlers and name not in BLOCKED_TOOL_NAMES

    def requires_confirm(self, name: str) -> bool:
        return name in CONFIRM_REQUIRED_TOOLS

    async def execute(
        self,
        name: str,
        args: dict,
        *,
        confirmed: bool = False,
    ) -> dict:
        if not self.is_allowed(name):
            return {"ok": False, "error": f"Narzędzie niedozwolone: {name}"}
        if self.requires_confirm(name) and not confirmed:
            return {
                "ok": False,
                "needs_confirm": True,
                "tool": name,
                "args": args,
                "message": f"Akcja '{name}' wymaga potwierdzenia użytkownika.",
            }
        handler = self._handlers[name]
        try:
            if inspect.iscoroutinefunction(handler):
                result = await handler(args)
            else:
                result = handler(args)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    async def _get_health(self, _args: dict) -> dict:
        return await BielikClient(self.settings).healthcheck_extended()

    def _get_inbox_counts(self, _args: dict) -> dict:
        return InboxService(self.settings).get_counts()

    def _list_inbox_jobs(self, args: dict) -> dict:
        svc = InboxService(self.settings)
        limit = int(args.get("limit") or 10)
        tier = args.get("tier")
        if tier:
            data = svc.load_inbox(
                tier=tier,
                status=args.get("status"),
                fit=args.get("fit"),
                q=args.get("q"),
            )
        else:
            data = svc.list_jobs(status=args.get("status"), fit=args.get("fit"), q=args.get("q"))
        jobs = data.get("jobs", [])[:limit]
        return {"total": data.get("total", len(jobs)), "jobs": jobs}

    async def _list_applications(self, args: dict) -> dict:
        limit = int(args.get("limit") or 20)
        apps = await ApplicationService(self.settings).list(
            hiring_stage=args.get("hiring_stage"),
            limit=limit,
        )
        slim = [
            {
                "id": a.get("id"),
                "company": a.get("company"),
                "role": a.get("role"),
                "hiring_stage": a.get("hiring_stage"),
                "pipeline_stage": a.get("pipeline_stage"),
                "pipeline_status": a.get("pipeline_status"),
                "url": a.get("url"),
            }
            for a in apps
        ]
        return {"applications": slim, "count": len(slim)}

    async def _get_application(self, args: dict) -> dict:
        app_id = int(args.get("application_id") or 0)
        if not app_id:
            raise ValueError("application_id jest wymagane")
        app = await ApplicationService(self.settings).get(app_id)
        if not app:
            raise ValueError(f"Nie znaleziono aplikacji {app_id}")
        return app.model_dump()

    def _get_setup_state(self, _args: dict) -> dict:
        profile = ProfileService(self.settings)
        status = profile.get_status()
        state = profile.load_wizard_state()
        return {
            "profile_status": status,
            "wizard_path": state.path,
            "sections_completed": status.get("sections_done", []),
        }

    async def _get_dashboard(self, _args: dict) -> dict:
        return await DashboardService(self.settings).summary()

    async def _search_memory(self, args: dict) -> dict:
        if not self.memory:
            return {"facts": []}
        query = str(args.get("query") or "")
        facts = await self.memory.search_facts(query)
        return {"facts": facts}

    def _skip_inbox_job(self, args: dict) -> dict:
        url = str(args.get("url") or "").strip()
        if not url:
            raise ValueError("url jest wymagane")
        svc = InboxService(self.settings)
        found = svc.repo.get_by_url(url)
        if not found:
            raise ValueError(f"Nie znaleziono oferty: {url}")
        _key, job = found
        if job.status == "evaluated":
            raise ValueError(
                "Nie można pominąć oferty ze statusem evaluated (wpis trackera)"
            )
        if job.status != "new":
            raise ValueError(f"skip dozwolony tylko dla status=new (obecny: {job.status})")
        reason = str(args.get("reason") or "Pominięte przez asystenta")
        update = SeenJobUpdate(
            status="skipped",
            skip_reason=SkipReasonDetails(
                reasons=[ManualSkipReasonItem(category="other", comment=reason)]
            ),
        )
        ok = svc.update_job(url, update)
        return {"skipped": ok, "url": url}

    async def _evaluate_job(self, args: dict) -> dict:
        url = str(args.get("url") or "").strip()
        if not url:
            raise ValueError("url jest wymagane")
        task_id = await TaskService.get().create("apply")
        pipeline = PipelineService(self.settings)
        apply_req = ApplyRequest(url=url, proceed=False, compile_pdf=False)
        ctx = await pipeline.create_application(apply_req, task_id=task_id)
        asyncio.create_task(self._run_evaluate_task(task_id, apply_req, ctx.application_id, ctx.run_id))
        return {
            "task_id": task_id,
            "application_id": ctx.application_id,
            "kind": "apply",
            "status": "running",
        }

    async def _run_evaluate_task(
        self, task_id: str, apply_req: ApplyRequest, application_id: int, run_id: int
    ) -> None:
        from app.api.routes_apply import _run_apply_task

        await _run_apply_task(task_id, ApplyAsyncRequest(url=apply_req.url, proceed=False), application_id, run_id)

    async def _run_triage_async(self, _args: dict) -> dict:
        from app.api.routes_inbox import _run_triage_task

        task_id = await TaskService.get().create("triage")
        asyncio.create_task(_run_triage_task(task_id))
        return {"task_id": task_id, "kind": "triage", "status": "running"}

    async def _start_scrape_async(self, args: dict) -> dict:
        from app.api.routes_scrape import _run_scrape_task

        request = ScrapeRequest(
            query=args.get("query"),
            broad=bool(args.get("broad")),
        )
        task_id = await TaskService.get().create("scrape")
        asyncio.create_task(_run_scrape_task(task_id, request))
        return {"task_id": task_id, "kind": "scrape", "status": "running"}

    async def _update_hiring_stage(self, args: dict) -> dict:
        app_id = int(args.get("application_id") or 0)
        stage = str(args.get("hiring_stage") or "")
        if not app_id or stage not in HIRING_STAGES:
            raise ValueError("application_id i prawidłowy hiring_stage są wymagane")
        ok = await ApplicationService(self.settings).update(app_id, hiring_stage=stage)
        return {"updated": ok, "application_id": app_id, "hiring_stage": stage}

    async def _add_application_note(self, args: dict) -> dict:
        app_id = int(args.get("application_id") or 0)
        body = str(args.get("body") or "").strip()
        if not app_id or not body:
            raise ValueError("application_id i body są wymagane")
        svc = ApplicationService(self.settings)
        await svc.db.add_application_activity(app_id, kind="note", body=body, author="assistant")
        return {"application_id": app_id, "note_added": True}

    async def _remember_fact(self, args: dict) -> dict:
        if not self.memory:
            raise ValueError("Pamięć niedostępna")
        return await self.memory.remember_fact(
            category=str(args.get("category") or "context"),
            key=str(args.get("key") or ""),
            content=str(args.get("content") or ""),
        )

    async def _start_full_apply(self, args: dict) -> dict:
        url = str(args.get("url") or "").strip()
        if not url:
            raise ValueError("url jest wymagane")
        task_id = await TaskService.get().create("apply")
        pipeline = PipelineService(self.settings)
        apply_req = ApplyRequest(url=url, proceed=True, compile_pdf=True)
        ctx = await pipeline.create_application(apply_req, task_id=task_id)
        from app.api.routes_apply import _run_apply_task

        asyncio.create_task(
            _run_apply_task(
                task_id,
                ApplyAsyncRequest(url=url, proceed=True, compile_pdf=True),
                ctx.application_id,
                ctx.run_id,
            )
        )
        return {
            "task_id": task_id,
            "application_id": ctx.application_id,
            "kind": "apply",
            "status": "running",
        }

    def _reset_data(self, args: dict) -> dict:
        token = str(args.get("confirm_token") or "")
        if token != "RESET":
            raise ValueError("reset wymaga confirm_token=RESET")
        result = ResetService(self.settings).execute(
            ResetExecuteRequest(scope="all", confirmation="RESET")
        )
        return result.model_dump()

    def _expand_apply_profile(self, _args: dict) -> dict:
        return ExpandService(self.settings).apply(ExpandApplyRequest(apply_all=True)).model_dump()
