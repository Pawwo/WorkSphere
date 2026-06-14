from __future__ import annotations

import aiosqlite
from pathlib import Path
from typing import Any, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    query TEXT,
    broad INTEGER NOT NULL DEFAULT 0,
    portals TEXT,
    total_found INTEGER NOT NULL DEFAULT 0,
    new_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'completed',
    portal_status TEXT
);

CREATE TABLE IF NOT EXISTS apply_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    company TEXT,
    role TEXT,
    url TEXT,
    stage TEXT NOT NULL DEFAULT 'started',
    status TEXT NOT NULL DEFAULT 'started',
    result_json TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    stage TEXT NOT NULL DEFAULT '',
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    task_id TEXT,
    url TEXT,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    company_slug TEXT,
    pipeline_stage TEXT NOT NULL DEFAULT 'parse',
    pipeline_status TEXT NOT NULL DEFAULT 'pending',
    hiring_stage TEXT NOT NULL DEFAULT 'draft',
    overall_fit TEXT,
    fit_score TEXT,
    recommendation TEXT,
    reviewer_verdict TEXT,
    verification_pass INTEGER,
    cv_file TEXT,
    cover_file TEXT,
    pdf_cv TEXT,
    pdf_cover TEXT,
    interview_prep_file TEXT,
    application_dir TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS application_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'stage_log',
    author TEXT NOT NULL DEFAULT 'system',
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (application_id) REFERENCES applications(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_applications_url ON applications(url) WHERE url IS NOT NULL AND url != '';

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT '',
    progress INTEGER NOT NULL DEFAULT 0,
    message TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running',
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id, id);

CREATE TABLE IF NOT EXISTS assistant_threads (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'Główna',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assistant_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES assistant_threads(id)
);

CREATE INDEX IF NOT EXISTS idx_assistant_messages_thread ON assistant_messages(thread_id, id);

CREATE TABLE IF NOT EXISTS assistant_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL DEFAULT 'context',
    key TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    source_message_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assistant_tool_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    args_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    status TEXT NOT NULL DEFAULT 'ok',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_assistant_tool_runs_thread ON assistant_tool_runs(thread_id, id);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    async def _ensure_scrape_runs_schema(self, conn: aiosqlite.Connection) -> None:
        await conn.executescript(SCHEMA)
        cursor = await conn.execute("PRAGMA table_info(scrape_runs)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "portal_status" not in columns:
            await conn.execute("ALTER TABLE scrape_runs ADD COLUMN portal_status TEXT")

    async def create_scrape_run(
        self,
        *,
        query: Optional[str],
        broad: bool,
        portals: str,
        total_found: int,
        new_count: int,
        portal_status: Optional[str] = None,
    ) -> int:
        from datetime import datetime, timezone

        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_scrape_runs_schema(conn)
            cursor = await conn.execute(
                """
                INSERT INTO scrape_runs (created_at, query, broad, portals, total_found, new_count, portal_status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    query,
                    1 if broad else 0,
                    portals,
                    total_found,
                    new_count,
                    portal_status,
                ),
            )
            await conn.commit()
            return cursor.lastrowid or 0

    async def create_apply_run(
        self,
        *,
        company: Optional[str],
        role: Optional[str],
        url: Optional[str],
        stage: str,
        result_json: Optional[str] = None,
        status: str = "started",
    ) -> int:
        from datetime import datetime, timezone

        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as conn:
            await conn.executescript(SCHEMA)
            cursor = await conn.execute(
                """
                INSERT INTO apply_runs (created_at, company, role, url, stage, status, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    company,
                    role,
                    url,
                    stage,
                    status,
                    result_json,
                ),
            )
            await conn.commit()
            return cursor.lastrowid or 0

    async def update_apply_run(
        self,
        run_id: int,
        *,
        stage: str,
        status: str,
        result_json: str,
    ) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                """
                UPDATE apply_runs SET stage = ?, status = ?, result_json = ? WHERE id = ?
                """,
                (stage, status, result_json, run_id),
            )
            await conn.commit()

    async def get_apply_run(self, run_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executescript(SCHEMA)
            cursor = await conn.execute("SELECT * FROM apply_runs WHERE id = ?", (run_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_apply_runs(self, limit: int = 20) -> list:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executescript(SCHEMA)
            cursor = await conn.execute(
                "SELECT id, created_at, company, role, stage, status FROM apply_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def create_task(self, task_id: str, kind: str) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as conn:
            await conn.executescript(SCHEMA)
            await conn.execute(
                """
                INSERT INTO tasks (id, kind, status, stage, progress, message, created_at, updated_at)
                VALUES (?, ?, 'running', 'start', 0, '', ?, ?)
                """,
                (task_id, kind, now, now),
            )
            await conn.commit()

    async def update_task(
        self,
        task_id: str,
        *,
        stage: str,
        progress: int,
        message: str,
        status: str,
        result_json: Optional[str] = None,
    ) -> None:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                """
                UPDATE tasks SET stage=?, progress=?, message=?, status=?, result_json=?, updated_at=?
                WHERE id=?
                """,
                (stage, progress, message, status, result_json, now, task_id),
            )
            await conn.commit()

    async def get_task(self, task_id: str) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executescript(SCHEMA)
            cursor = await conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def append_task_event(
        self,
        task_id: str,
        *,
        stage: str,
        progress: int,
        message: str,
        status: str,
        payload: Optional[dict] = None,
    ) -> None:
        import json

        now = self._now_iso()
        payload_json = json.dumps(payload, ensure_ascii=False, default=str) if payload else None
        async with aiosqlite.connect(self.path) as conn:
            await conn.executescript(SCHEMA)
            await conn.execute(
                """
                INSERT INTO task_events (task_id, stage, progress, message, status, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, stage, progress, message, status, payload_json, now),
            )
            await conn.commit()

    async def list_task_events(self, task_id: str) -> list[dict]:
        import json

        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executescript(SCHEMA)
            cursor = await conn.execute(
                "SELECT stage, progress, message, status, payload_json FROM task_events WHERE task_id = ? ORDER BY id",
                (task_id,),
            )
            rows = []
            for row in await cursor.fetchall():
                item = {
                    "stage": row["stage"],
                    "progress": row["progress"],
                    "message": row["message"],
                    "status": row["status"],
                }
                if row["payload_json"]:
                    try:
                        extra = json.loads(row["payload_json"])
                        if isinstance(extra, dict):
                            item.update(extra)
                    except json.JSONDecodeError:
                        pass
                rows.append(item)
            return rows

    async def list_scrape_runs(self, limit: int = 10) -> list:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.executescript(SCHEMA)
            cursor = await conn.execute(
                "SELECT * FROM scrape_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def _ensure_schema(self, conn: aiosqlite.Connection) -> None:
        await self._ensure_scrape_runs_schema(conn)

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    async def create_application(
        self,
        *,
        company: str,
        role: str,
        url: Optional[str] = None,
        company_slug: Optional[str] = None,
        run_id: Optional[int] = None,
        task_id: Optional[str] = None,
        pipeline_stage: str = "parse",
        pipeline_status: str = "pending",
        hiring_stage: str = "draft",
        application_dir: Optional[str] = None,
    ) -> int:
        now = self._now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                INSERT INTO applications (
                    run_id, task_id, url, company, role, company_slug,
                    pipeline_stage, pipeline_status, hiring_stage, application_dir,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    url,
                    company,
                    role,
                    company_slug,
                    pipeline_stage,
                    pipeline_status,
                    hiring_stage,
                    application_dir,
                    now,
                    now,
                ),
            )
            await conn.commit()
            return cursor.lastrowid or 0

    async def update_application(self, app_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = self._now_iso()
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [app_id]
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            await conn.execute(f"UPDATE applications SET {cols} WHERE id = ?", vals)
            await conn.commit()

    async def get_application(self, app_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_schema(conn)
            cursor = await conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_application_by_url(self, url: str) -> Optional[dict]:
        if not url:
            return None
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                "SELECT * FROM applications WHERE url = ? ORDER BY id DESC LIMIT 1",
                (url,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_applications(
        self,
        *,
        hiring_stage: Optional[str] = None,
        pipeline_stage: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        clauses: list[str] = []
        params: list[Any] = []
        if hiring_stage:
            clauses.append("hiring_stage = ?")
            params.append(hiring_stage)
        if pipeline_stage:
            clauses.append("pipeline_stage = ?")
            params.append(pipeline_stage)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                f"SELECT * FROM applications {where} ORDER BY updated_at DESC LIMIT ?",
                params,
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def count_applications_by_hiring_stage(self) -> dict:
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                "SELECT hiring_stage, COUNT(*) as cnt FROM applications GROUP BY hiring_stage"
            )
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    async def add_application_activity(
        self,
        application_id: int,
        *,
        kind: str,
        body: str,
        author: str = "system",
    ) -> int:
        now = self._now_iso()
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                INSERT INTO application_activities (application_id, kind, author, body, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (application_id, kind, author, body, now),
            )
            await conn.commit()
            return cursor.lastrowid or 0

    async def list_application_activities(self, application_id: int, limit: int = 50) -> list:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                SELECT * FROM application_activities
                WHERE application_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (application_id, limit),
            )
            return [dict(r) for r in await cursor.fetchall()]

    # --- Assistant tables ---

    async def ensure_assistant_thread(self, thread_id: str, title: str = "Główna") -> None:
        now = self._now_iso()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                "SELECT id FROM assistant_threads WHERE id = ?", (thread_id,)
            )
            if await cursor.fetchone():
                return
            await conn.execute(
                """
                INSERT INTO assistant_threads (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (thread_id, title, now, now),
            )
            await conn.commit()

    async def touch_assistant_thread(self, thread_id: str) -> None:
        now = self._now_iso()
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            await conn.execute(
                "UPDATE assistant_threads SET updated_at = ? WHERE id = ?",
                (now, thread_id),
            )
            await conn.commit()

    async def add_assistant_message(
        self,
        thread_id: str,
        *,
        role: str,
        content: str,
        tool_calls_json: Optional[str] = None,
    ) -> int:
        now = self._now_iso()
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                INSERT INTO assistant_messages (thread_id, role, content, tool_calls_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (thread_id, role, content, tool_calls_json, now),
            )
            await conn.execute(
                "UPDATE assistant_threads SET updated_at = ? WHERE id = ?",
                (now, thread_id),
            )
            await conn.commit()
            return cursor.lastrowid or 0

    async def list_assistant_messages(self, thread_id: str, limit: int = 50) -> list[dict]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                SELECT id, thread_id, role, content, tool_calls_json, created_at
                FROM assistant_messages
                WHERE thread_id = ?
                ORDER BY id DESC LIMIT ?
                """,
                (thread_id, limit),
            )
            rows = [dict(r) for r in await cursor.fetchall()]
            rows.reverse()
            return rows

    async def add_assistant_memory(
        self,
        *,
        category: str,
        key: str,
        content: str,
        source_message_id: Optional[int] = None,
    ) -> int:
        now = self._now_iso()
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                INSERT INTO assistant_memory (category, key, content, source_message_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (category, key, content, source_message_id, now, now),
            )
            await conn.commit()
            return cursor.lastrowid or 0

    async def list_assistant_memory(self, limit: int = 100) -> list[dict]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                SELECT id, category, key, content, source_message_id, created_at, updated_at
                FROM assistant_memory
                ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def search_assistant_memory(self, query: str, limit: int = 20) -> list[dict]:
        q = f"%{query.lower()}%"
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                SELECT id, category, key, content, created_at, updated_at
                FROM assistant_memory
                WHERE lower(key) LIKE ? OR lower(content) LIKE ? OR lower(category) LIKE ?
                ORDER BY updated_at DESC LIMIT ?
                """,
                (q, q, q, limit),
            )
            return [dict(r) for r in await cursor.fetchall()]

    async def delete_assistant_memory(self, memory_id: int) -> bool:
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                "DELETE FROM assistant_memory WHERE id = ?", (memory_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def count_assistant_memory(self) -> int:
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute("SELECT COUNT(*) FROM assistant_memory")
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def add_assistant_tool_run(
        self,
        thread_id: str,
        *,
        tool_name: str,
        args_json: str,
        result_json: Optional[str] = None,
        status: str = "ok",
    ) -> int:
        now = self._now_iso()
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                """
                INSERT INTO assistant_tool_runs (thread_id, tool_name, args_json, result_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (thread_id, tool_name, args_json, result_json, status, now),
            )
            await conn.commit()
            return cursor.lastrowid or 0

    async def get_assistant_tool_run(self, run_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            await self._ensure_schema(conn)
            cursor = await conn.execute(
                "SELECT * FROM assistant_tool_runs WHERE id = ?", (run_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_assistant_tool_run(
        self,
        run_id: int,
        *,
        result_json: str,
        status: str,
    ) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await self._ensure_schema(conn)
            await conn.execute(
                """
                UPDATE assistant_tool_runs SET result_json = ?, status = ? WHERE id = ?
                """,
                (result_json, status, run_id),
            )
            await conn.commit()
