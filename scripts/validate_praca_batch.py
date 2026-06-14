#!/usr/bin/env python3
"""Mini-batch validation: praca-pl listing-only under batch settings."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.scrapers.bun_cli import BunCLIError, BunCLIWrapper

QUERIES = [
    '"Chief Operating Officer (COO)" Szczecin/Warszawa',
    '"ERP Operations Manager" Szczecin/Warszawa',
    '"Dyrektor Operacyjny" Szczecin/Warszawa',
    '"Head of Operations" Szczecin/Warszawa',
    '"AI Process Automation" Szczecin/Warszawa',
    '"Senior AI Product Manager" Szczecin/Warszawa',
    '"BPMN" Szczecin/Warszawa',
    '"Digital Transformation Strategist" Szczecin/Warszawa',
]


async def main() -> int:
    cli = BunCLIWrapper()
    timeouts = 0
    total_results = 0
    t0 = time.perf_counter()
    for i, query in enumerate(QUERIES, 1):
        tq = time.perf_counter()
        try:
            resp = await cli.search("praca-pl", query, days=2, limit=20, is_batch=True)
            n = len(resp.results)
            total_results += n
            status = f"OK {n} results"
        except BunCLIError as exc:
            if exc.code == "TIMEOUT":
                timeouts += 1
            status = f"ERR {exc.code}: {exc}"
        elapsed = time.perf_counter() - tq
        print(f"[{i}/{len(QUERIES)}] {elapsed:.1f}s {status} — {query[:50]}")
    wall = time.perf_counter() - t0
    print(f"\nSummary: queries={len(QUERIES)} timeouts={timeouts} results={total_results} wall={wall:.1f}s")
    print("Baseline (task 12358880): 61/64 praca-pl TIMEOUTs, ~90s each")
    return 1 if timeouts else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
