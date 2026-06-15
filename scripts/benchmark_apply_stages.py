#!/usr/bin/env python3
"""Print stage_timings and draft sub-stage gaps from apply runs."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    s = value.replace("+00:00", "").replace("Z", "")
    if "." in s:
        base, frac = s.split(".", 1)
        s = f"{base}.{frac[:6]}"
    return datetime.fromisoformat(s)


def _draft_substage_gaps(events: list[sqlite3.Row]) -> list[tuple[str, float, str]]:
    """Return (label, seconds, message) for draft-related SSE gaps."""
    draft_events = [
        e
        for e in events
        if e["stage"] == "draft" or (e["stage"] == "parse" and "Budzenie" in (e["message"] or ""))
    ]
    if not draft_events:
        return []

    gaps: list[tuple[str, float, str]] = []
    prev_ts: datetime | None = None
    prev_msg = ""
    for e in draft_events:
        ts = _parse_ts(e["created_at"])
        msg = e["message"] or ""
        if prev_ts and ts:
            gap = (ts - prev_ts).total_seconds()
            label = prev_msg or "start"
            if msg.startswith("draft:"):
                label = prev_msg if prev_msg.startswith("draft:") else label
            gaps.append((label, gap, msg))
        prev_ts = ts
        prev_msg = msg
    return gaps


def _resolve_task_id(conn: sqlite3.Connection, app_id: int, task_id: str | None) -> str | None:
    if task_id:
        return task_id
    row = conn.execute("SELECT task_id FROM applications WHERE id=?", (app_id,)).fetchone()
    return row["task_id"] if row and row["task_id"] else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark apply pipeline stage timings")
    parser.add_argument("application_id", type=int, nargs="?", default=None)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "app.db")
    parser.add_argument("--task-id", dest="task_id", default=None, help="Task UUID for sub-stage SSE gaps")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    if args.application_id:
        row = conn.execute(
            "SELECT id, company, role, run_id, task_id FROM applications WHERE id=?",
            (args.application_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, company, role, run_id, task_id FROM applications ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        print("No application found")
        return

    run = conn.execute(
        "SELECT result_json FROM apply_runs WHERE id=?", (row["run_id"],)
    ).fetchone()
    timings: dict[str, int] = {}
    if run and run["result_json"]:
        data = json.loads(run["result_json"])
        timings = data.get("stage_timings") or {}

    print(f"Application {row['id']}: {row['company']} — {row['role']}")

    task_id = _resolve_task_id(conn, row["id"], args.task_id or row["task_id"])
    if task_id:
        events = conn.execute(
            "SELECT stage, status, message, progress, created_at FROM task_events "
            "WHERE task_id=? ORDER BY rowid",
            (task_id,),
        ).fetchall()
        if events:
            print(f"Task {task_id}")
            first_ts = _parse_ts(events[0]["created_at"])
            last_ts = _parse_ts(events[-1]["created_at"])
            if first_ts and last_ts:
                print(f"  Wall clock: {(last_ts - first_ts).total_seconds():.1f}s")
            sub = _draft_substage_gaps(events)
            if sub:
                print("  Draft sub-stages (gaps between SSE events):")
                for label, sec, nxt in sub:
                    short = label[:48] + "…" if len(label) > 48 else label
                    print(f"    {sec:6.1f}s  after «{short}» → {nxt}")

    if not timings:
        print("No stage_timings (pipeline may still be running)")
        return

    total_ms = sum(timings.values())
    for stage, ms in timings.items():
        pct = (ms / total_ms * 100) if total_ms else 0
        print(f"  {stage:16} {ms/1000:6.1f}s  ({pct:4.0f}%)")
    print(f"  {'TOTAL':16} {total_ms/1000:6.1f}s")

    draft_ms = timings.get("draft", 0)
    if draft_ms > 90_000:
        print(
            "\n  Hint: draft >90s — check LLM load and config.yaml llm.concurrency"
        )


if __name__ == "__main__":
    main()
