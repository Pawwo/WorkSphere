"""Migration applied+done → ready_to_send."""

from datetime import datetime, timezone

import aiosqlite
import pytest

from scripts.migrate_hiring_ready_to_send import migrate
from app.storage.db import SCHEMA


@pytest.mark.asyncio
async def test_migrate_hiring_ready_to_send(tmp_path):
    db_path = tmp_path / "app.db"
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(SCHEMA)
        rows = [
            (1, "A", "R1", "done", "done", "applied"),
            (2, "B", "R2", "done", "done", "screening"),
            (3, "C", "R3", "draft", "running", "applied"),
            (4, "D", "R4", "done", "done", "applied"),
        ]
        for app_id, company, role, p_stage, p_status, hiring in rows:
            await conn.execute(
                """
                INSERT INTO applications (
                    id, company, role, pipeline_stage, pipeline_status,
                    hiring_stage, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (app_id, company, role, p_stage, p_status, hiring, now, now),
            )
        await conn.commit()

    n = await migrate(db_path)
    assert n == 2

    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT id, hiring_stage FROM applications ORDER BY id"
        )
        by_id = {row["id"]: row["hiring_stage"] for row in await cur.fetchall()}

    assert by_id[1] == "ready_to_send"
    assert by_id[2] == "screening"
    assert by_id[3] == "applied"
    assert by_id[4] == "ready_to_send"
