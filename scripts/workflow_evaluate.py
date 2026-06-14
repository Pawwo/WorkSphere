#!/usr/bin/env python3
"""Pełna ocena dopasowania (proceed=false) dla kolejki z evaluate_queue.json."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.apply import ApplyRequest
from app.services.apply_service import ApplyService

QUEUE_PATH = ROOT / "data" / "job_scraper" / "evaluate_queue.json"
RESULTS_PATH = ROOT / "data" / "job_scraper" / "evaluate_results.json"


def overall_score(evaluation) -> int:
    if not evaluation:
        return 0
    scores = []
    for field in ("skills_match", "experience_match", "behavioral_match"):
        block = getattr(evaluation, field, None) or {}
        if isinstance(block, dict) and isinstance(block.get("score"), (int, float)):
            scores.append(int(block["score"]))
    if scores:
        return sum(scores) // len(scores)
    if evaluation.overall_fit == "strong":
        return 80
    if evaluation.overall_fit == "moderate":
        return 55
    return 35


async def main() -> None:
    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    urls = queue.get("urls", [])
    svc = ApplyService()
    results: list[dict] = []

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] Evaluating {url[:70]}...")
        try:
            resp = await svc.run(ApplyRequest(url=url, proceed=False, compile_pdf=False))
            ev = resp.evaluation
            score = overall_score(ev)
            row = {
                "url": url,
                "role": resp.parsed.role,
                "company": resp.parsed.company,
                "overall_fit": ev.overall_fit if ev else "unknown",
                "overall_score": score,
                "skills_score": (ev.skills_match or {}).get("score") if ev else None,
                "recommendation": ev.recommendation if ev else resp.message,
                "run_id": resp.run_id,
                "warnings": resp.warnings,
            }
            results.append(row)
            print(f"  -> {row['overall_fit']} score={score} | {row['role'][:50]}")
        except Exception as exc:
            results.append({"url": url, "error": str(exc), "overall_score": 0})
            print(f"  -> ERROR: {exc}")

    results.sort(key=lambda x: x.get("overall_score", 0), reverse=True)
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {RESULTS_PATH}")
    print("Top 3 for apply:")
    for r in results[:3]:
        if r.get("overall_score", 0) >= 60 or r.get("overall_fit") == "strong":
            print(f"  score={r.get('overall_score')} {r.get('company')} — {r.get('url', '')[:60]}")


if __name__ == "__main__":
    asyncio.run(main())
