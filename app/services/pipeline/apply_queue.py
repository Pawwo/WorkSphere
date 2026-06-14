"""Serialize LLM-heavy apply stages and recover stale tasks."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator, Awaitable, Callable, Optional

import aiosqlite

from app.config import Settings, get_settings
from app.storage.db import SCHEMA

logger = logging.getLogger(__name__)

_LLM_PIPELINE_LOCK = asyncio.Lock()
_waiting_count = 0


@asynccontextmanager
async def llm_pipeline_slot(
    *,
    on_waiting: Optional[Callable[[int], Awaitable[None]]] = None,
) -> AsyncIterator[None]:
    """One apply draft/review at a time when LLM concurrency is 1."""
    global _waiting_count
    acquired = _LLM_PIPELINE_LOCK.locked()
    if acquired:
        _waiting_count += 1
        position = _waiting_count
        if on_waiting:
            await on_waiting(position)
        logger.info("Apply waiting for LLM pipeline slot (queue position %s)", position)
    try:
        if acquired:
            await _LLM_PIPELINE_LOCK.acquire()
            _waiting_count = max(0, _waiting_count - 1)
        else:
            await _LLM_PIPELINE_LOCK.acquire()
        yield
    finally:
        _LLM_PIPELINE_LOCK.release()


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


async def recover_stale_apply_tasks(
    settings: Optional[Settings] = None,
    *,
    db_path: Optional[Path] = None,
) -> int:
    """Mark hung apply tasks failed when no task_events for stale_task_seconds."""
    settings = settings or get_settings()
    timeout = max(60, int(getattr(settings, "pipeline_stale_task_seconds", 300) or 300))
    recovered = 0
    now = datetime.now(timezone.utc)
    db_file = db_path or settings.db_path
    async with aiosqlite.connect(db_file) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.executescript(SCHEMA)
        cursor = await conn.execute(
            """
            SELECT t.id AS task_id, t.stage, t.updated_at, a.id AS application_id
            FROM tasks t
            LEFT JOIN applications a ON a.task_id = t.id
            WHERE t.status = 'running' AND t.kind = 'apply'
            """
        )
        rows = await cursor.fetchall()
        for row in rows:
            task_id = row["task_id"]
            ev_cursor = await conn.execute(
                "SELECT created_at FROM task_events WHERE task_id = ? ORDER BY id DESC LIMIT 1",
                (task_id,),
            )
            ev = await ev_cursor.fetchone()
            ref_ts = (ev["created_at"] if ev else None) or row["updated_at"]
            if not ref_ts:
                continue
            age = (now - _parse_iso(ref_ts)).total_seconds()
            if age < timeout:
                continue
            await conn.execute(
                "UPDATE tasks SET status='failed', message=?, updated_at=? WHERE id=?",
                (
                    f"Timeout — brak postępu przez {int(age)}s (limit {timeout}s). Użyj retry draft.",
                    now.isoformat(),
                    task_id,
                ),
            )
            app_id = row["application_id"]
            if app_id:
                await conn.execute(
                    """
                    UPDATE applications
                    SET pipeline_status='failed', pipeline_stage=?
                    WHERE id=?
                    """,
                    (row["stage"] or "draft", app_id),
                )
                await conn.execute(
                    """
                    INSERT INTO application_activities (application_id, kind, body, created_at)
                    VALUES (?, 'stage_log', ?, ?)
                    """,
                    (
                        app_id,
                        f"{row['stage'] or 'draft'}: timeout — retry recommended",
                        now.isoformat(),
                    ),
                )
            recovered += 1
            logger.warning("Recovered stale apply task %s (app %s, age %.0fs)", task_id, app_id, age)
        await conn.commit()
    return recovered


async def stale_task_watchdog_loop(settings: Optional[Settings] = None) -> None:
    settings = settings or get_settings()
    interval = 60
    while True:
        try:
            n = await recover_stale_apply_tasks(settings)
            if n:
                logger.info("Stale task watchdog recovered %s task(s)", n)
        except Exception as exc:
            logger.warning("Stale task watchdog error: %s", exc)
        await asyncio.sleep(interval)
