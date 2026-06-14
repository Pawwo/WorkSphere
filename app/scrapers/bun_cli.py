from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import List, Optional

from app.config import Settings, get_settings
from app.models.jobs import JobCard, SearchMeta, SearchResponse

logger = logging.getLogger(__name__)

PORTAL_SKILLS = {
    "pracuj": "pracuj-search",
    "praca_pl": "praca-pl-search",
    "praca-pl": "praca-pl-search",
    "justjoin": "justjoin-search",
    "nofluffjobs": "nofluffjobs-search",
    "theprotocol": "theprotocol-search",
    "rocketjobs": "rocketjobs-search",
    "indeed": "indeed-pl-search",
    "indeed-pl": "indeed-pl-search",
    "linkedin": "linkedin-pl-search",
    "linkedin-pl": "linkedin-pl-search",
}

FAST_PORTALS = {"pracuj", "praca_pl", "praca-pl", "theprotocol"}
SLOW_PORTALS = {"justjoin", "nofluffjobs", "rocketjobs"}
BROWSER_PORTALS = {"indeed", "indeed-pl", "linkedin", "linkedin-pl"}

RETRYABLE_CODES = {"TIMEOUT", "RATE_LIMITED"}


class BunCLIError(Exception):
    def __init__(self, portal: str, message: str, code: str = "API_ERROR"):
        super().__init__(message)
        self.portal = portal
        self.code = code


def nfj_category_for_query(query: str) -> str:
    q = query.lower()
    if "odoo" in q or "erp" in q:
        return "backend"
    if "coo" in q or "operations" in q or "director" in q:
        return "architecture"
    if "ai" in q or "machine learning" in q:
        return "ai"
    if "devops" in q or "sre" in q:
        return "devops"
    if "frontend" in q or "react" in q:
        return "frontend"
    if "data" in q or "analyst" in q:
        return "data"
    return "ai"


class BunCLIWrapper:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.bun = self.settings.bun_path
        self.repo_root = self.settings.repo_root

    def _cli_path(self, skill_name: str) -> Path:
        return self.repo_root / self.settings.scrapers_skills_dir / skill_name / "cli" / "src" / "cli.ts"

    def _portal_timeout(self, portal_key: str) -> int:
        normalized = portal_key.replace("_", "-")
        overrides = self.settings.scrapers_portal_timeouts
        for key in (portal_key, normalized, portal_key.replace("-", "_")):
            if key in overrides:
                return overrides[key]
        return self.settings.scrapers_portal_timeout_seconds

    def _skill_name(self, portal_key: str) -> str:
        skill = PORTAL_SKILLS.get(portal_key, portal_key)
        if not skill.endswith("-search"):
            skill = f"{portal_key}-search"
        return skill

    def _portal_cli_args(self, portal_key: str, query: str, *, is_batch: bool = False) -> List[str]:
        extra: List[str] = []
        normalized = portal_key.replace("_", "-")
        if normalized in {"justjoin", "rocketjobs", "nofluffjobs"}:
            extra.extend(["--listing-only", "true"])
        if normalized == "praca-pl":
            extra.extend(["--listing-only", "true" if is_batch else "false"])
        if normalized == "nofluffjobs":
            extra.extend(["--category", nfj_category_for_query(query)])
        if normalized == "linkedin-pl":
            extra.extend(
                [
                    "--detail-limit",
                    str(self.settings.scrapers_linkedin_detail_limit),
                    "--pages",
                    str(self.settings.scrapers_linkedin_pages),
                ]
            )
        if normalized == "indeed-pl" and is_batch:
            extra.extend(["--detail-limit", "0"])
        return extra

    def _portal_strict(self, portal_key: str) -> bool:
        from app.services.scrape.freshness import portal_strict_freshness

        return portal_strict_freshness(
            portal_key,
            global_strict=self.settings.scrapers_strict_freshness,
            portal_overrides=self.settings.scrapers_portal_strict_freshness,
        )

    async def _search_once(
        self,
        portal_key: str,
        query: str,
        *,
        days: int,
        limit: int,
        page: int,
        max_age_hours: int = 0,
        is_batch: bool = False,
    ) -> SearchResponse:
        skill = self._skill_name(portal_key)
        cli_path = self._cli_path(skill)
        if not cli_path.exists():
            raise BunCLIError(portal_key, f"CLI not found: {cli_path}")

        cmd = [
            self.bun,
            "run",
            str(cli_path),
            "search",
            "--query",
            query,
            "--days",
            str(days),
            "--page",
            str(page),
            "--limit",
            str(limit),
            "--format",
            "json",
            *self._portal_cli_args(portal_key, query, is_batch=is_batch),
        ]
        hours = max_age_hours or self.settings.scrapers_max_age_hours
        if hours > 0:
            cmd.extend(["--max-age-hours", str(hours)])
        cmd.extend(
            ["--strict-freshness", "true" if self._portal_strict(portal_key) else "false"]
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self.settings.skills_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timeout = self._portal_timeout(portal_key)
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            raise BunCLIError(
                portal_key,
                f"Timeout po {timeout}s",
                "TIMEOUT",
            )
        if proc.returncode != 0:
            err_text = stderr.decode().strip()
            try:
                err_json = json.loads(err_text)
                raise BunCLIError(portal_key, err_json.get("error", err_text), err_json.get("code", "API_ERROR"))
            except json.JSONDecodeError:
                raise BunCLIError(portal_key, err_text or f"exit {proc.returncode}")

        data = json.loads(stdout.decode())
        return SearchResponse(
            meta=SearchMeta(**data["meta"]),
            results=[JobCard(**r) for r in data.get("results", [])],
        )

    async def search(
        self,
        portal_key: str,
        query: str,
        *,
        days: int = 14,
        limit: int = 20,
        page: int = 1,
        max_age_hours: int = 0,
        is_batch: bool = False,
    ) -> SearchResponse:
        retries = 0 if is_batch else max(0, self.settings.scrapers_retry_on_timeout)
        attempt = 0
        current_limit = limit
        last_error: Optional[BunCLIError] = None
        hours = max_age_hours or self.settings.scrapers_max_age_hours

        while attempt <= retries:
            try:
                return await self._search_once(
                    portal_key,
                    query,
                    days=days,
                    limit=current_limit,
                    page=page,
                    max_age_hours=hours,
                    is_batch=is_batch,
                )
            except BunCLIError as exc:
                last_error = exc
                if exc.code in RETRYABLE_CODES and attempt < retries:
                    current_limit = max(5, current_limit // 2)
                    logger.warning(
                        "Portal %s retry %s/%s (limit=%s): %s",
                        portal_key,
                        attempt + 1,
                        retries,
                        current_limit,
                        exc,
                    )
                    attempt += 1
                    await asyncio.sleep(1.0)
                    continue
                raise
        if last_error:
            raise last_error
        raise BunCLIError(portal_key, "Unknown search failure")

    async def search_parallel(
        self,
        portals: List[str],
        query: str,
        *,
        days: int = 14,
        limit: int = 20,
        is_batch: bool = False,
    ) -> List[tuple[str, SearchResponse | BunCLIError]]:
        return await self.search_parallel_tiered(
            portals, query, days=days, limit=limit, is_batch=is_batch
        )

    async def search_parallel_tiered(
        self,
        portals: List[str],
        query: str,
        *,
        days: int = 14,
        limit: int = 20,
        max_age_hours: int = 0,
        is_batch: bool = False,
    ) -> List[tuple[str, SearchResponse | BunCLIError]]:
        def norm(p: str) -> str:
            return p.replace("_", "-")

        fast = [p for p in portals if norm(p) in FAST_PORTALS]
        slow = [p for p in portals if norm(p) in SLOW_PORTALS]
        browser = [p for p in portals if norm(p) in BROWSER_PORTALS]
        known = set(fast + slow + browser)
        other = [p for p in portals if p not in known]
        parallel = max(1, self.settings.scrapers_parallel_limit)
        slow_parallel = (
            1
            if any(norm(p) == "rocketjobs" for p in slow)
            else max(1, min(2, parallel))
        )

        async def run_group(group: List[str], group_parallel: int) -> List[tuple[str, SearchResponse | BunCLIError]]:
            if not group:
                return []
            return await self._search_group(
                group,
                query,
                days=days,
                limit=limit,
                parallel=group_parallel,
                max_age_hours=max_age_hours,
                is_batch=is_batch,
            )

        if self.settings.scrapers_parallel_tier_groups:
            fast_res, slow_res, browser_res = await asyncio.gather(
                run_group(fast + other, parallel),
                run_group(slow, slow_parallel),
                run_group(browser, slow_parallel),
            )
            return [*fast_res, *slow_res, *browser_res]

        results: List[tuple[str, SearchResponse | BunCLIError]] = []
        results.extend(await run_group(fast + other, parallel))
        results.extend(await run_group(slow, slow_parallel))
        results.extend(await run_group(browser, slow_parallel))
        return results

    async def _search_group(
        self,
        portals: List[str],
        query: str,
        *,
        days: int,
        limit: int,
        parallel: int,
        max_age_hours: int = 0,
        is_batch: bool = False,
    ) -> List[tuple[str, SearchResponse | BunCLIError]]:
        if not portals:
            return []
        sem = asyncio.Semaphore(parallel)

        async def run_one(portal: str):
            async with sem:
                try:
                    result = await self.search(
                        portal,
                        query,
                        days=days,
                        limit=limit,
                        max_age_hours=max_age_hours,
                        is_batch=is_batch,
                    )
                    return portal, result
                except BunCLIError as exc:
                    return portal, exc
                except Exception as exc:
                    return portal, BunCLIError(portal, str(exc))

        return list(await asyncio.gather(*(run_one(p) for p in portals)))

    async def healthcheck(self, *, dry_run: bool = False) -> dict:
        portal_status: dict[str, dict] = {}
        all_ok = True
        bun_ok = False
        try:
            proc = await asyncio.create_subprocess_exec(
                self.bun,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            bun_ok = proc.returncode == 0
        except Exception:
            bun_ok = False

        workspace_modules = self.settings.skills_path / "node_modules"
        workspace_ok = workspace_modules.is_dir()
        if not workspace_ok:
            all_ok = False

        disabled = {
            p.replace("_", "-") for p in (self.settings.scrapers_disabled_portals or [])
        }
        disabled_skills = {PORTAL_SKILLS.get(d, d) for d in disabled}

        for portal_key, skill in PORTAL_SKILLS.items():
            if portal_key != portal_key.replace("_", "-"):
                continue
            cli = self._cli_path(skill)
            exists = cli.exists()
            required = portal_key not in disabled and skill not in disabled_skills
            portal_status[portal_key] = {
                "cli_exists": exists,
                "required": required,
            }
            if required and not exists:
                all_ok = False

        if dry_run and bun_ok and workspace_ok:
            try:
                await asyncio.wait_for(
                    self._search_once("pracuj", "test", days=14, limit=1, page=1),
                    timeout=60,
                )
                portal_status["pracuj"]["dry_run"] = True
            except Exception as exc:
                portal_status["pracuj"]["dry_run"] = False
                portal_status["pracuj"]["dry_run_error"] = str(exc)
                all_ok = False

        return {
            "ok": bun_ok and all_ok and workspace_ok,
            "bun": bun_ok,
            "workspace_modules": workspace_ok,
            "skills_dir": str(self.settings.skills_path),
            "portals": portal_status,
        }
