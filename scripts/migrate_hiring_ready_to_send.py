#!/usr/bin/env python3
"""One-off migration: applied + pipeline done → ready_to_send."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import aiosqlite

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings

MIGRATE_SQL = """
UPDATE applications
SET hiring_stage = 'ready_to_send'
WHERE hiring_stage = 'applied'
  AND pipeline_stage = 'done'
  AND pipeline_status = 'done'
"""


async def migrate(db_path: Path) -> int:
    async with aiosqlite.connect(db_path) as conn:
        cur = await conn.execute(MIGRATE_SQL)
        await conn.commit()
        return cur.rowcount


def main() -> int:
    settings = get_settings()
    db_path = Path(settings.db_path)
    if not db_path.is_file():
        print(f"Database not found: {db_path}", file=sys.stderr)
        return 1
    n = asyncio.run(migrate(db_path))
    print(f"Migrated {n} application(s): applied → ready_to_send (pipeline done)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
