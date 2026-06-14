"""Apply queue and stale task recovery."""

import asyncio
from datetime import datetime, timezone

import pytest

from app.services.pipeline.apply_queue import llm_pipeline_slot, recover_stale_apply_tasks


@pytest.mark.asyncio
async def test_llm_pipeline_slot_serializes():
    order: list[str] = []

    async def worker(name: str) -> None:
        async with llm_pipeline_slot():
            order.append(f"{name}-in")
            await asyncio.sleep(0.05)
            order.append(f"{name}-out")

    await asyncio.gather(worker("a"), worker("b"))
    assert order.index("a-in") < order.index("a-out")
    assert order.index("b-in") < order.index("b-out")
    # One worker fully inside before the other enters
    assert (order[0].startswith("a") and order[1].startswith("a")) or (
        order[0].startswith("b") and order[1].startswith("b")
    )


@pytest.mark.asyncio
async def test_recover_stale_apply_tasks_marks_failed(tmp_path):
    import aiosqlite

    from app.config import Settings
    from app.storage.db import SCHEMA

    db_path = tmp_path / "app.db"
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(SCHEMA)
        old = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        await conn.execute(
            "INSERT INTO tasks (id, kind, status, stage, progress, message, created_at, updated_at) "
            "VALUES ('stale-task', 'apply', 'running', 'draft', 40, 'x', ?, ?)",
            (old, old),
        )
        await conn.execute(
            "INSERT INTO applications (id, company, role, task_id, pipeline_stage, pipeline_status, "
            "hiring_stage, created_at, updated_at) VALUES (1, 'Co', 'Role', 'stale-task', 'draft', "
            "'running', 'draft', ?, ?)",
            (old, old),
        )
        await conn.execute(
            "INSERT INTO task_events (task_id, stage, progress, message, status, created_at) "
            "VALUES ('stale-task', 'draft', 40, 'x', 'running', ?)",
            (old,),
        )
        await conn.commit()

    settings = Settings().model_copy(
        update={"data_dir": tmp_path, "pipeline_stale_task_seconds": 60}
    )
    n = await recover_stale_apply_tasks(settings, db_path=db_path)
    assert n == 1

    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT status FROM tasks WHERE id='stale-task'")
        row = await cur.fetchone()
        assert row["status"] == "failed"
