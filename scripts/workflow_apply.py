#!/usr/bin/env python3
"""Pełny apply (proceed=true) dla top N ofert z evaluate_results + triage."""

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
APPLY_PATH = ROOT / "data" / "job_scraper" / "apply_results.json"
SEEN_PATH = ROOT / "data" / "job_scraper" / "seen_jobs.json"

MIN_SCORE = 75
FALLBACK_TOP_N = 3  # gdy LLM zwraca fallback 60, użyj triage top 3


def pick_urls() -> list[dict]:
    eval_results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    strong = [r for r in eval_results if r.get("overall_score", 0) >= MIN_SCORE]
    if strong:
        return strong[:3]

    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    jobs = queue.get("jobs", [])[:FALLBACK_TOP_N]
    return [
        {
            "url": j["url"],
            "title": j["title"],
            "company": j["company"],
            "overall_score": j.get("triage_score", 0),
            "note": "apply via triage (LLM evaluate fallback)",
        }
        for j in jobs
    ]


def mark_evaluated(url: str) -> None:
    data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
    seen = data.get("seen", data)
    for key, job in seen.items():
        if job.get("url") == url or key == url:
            job["status"] = "evaluated"
            break
    SEEN_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def main() -> None:
    targets = pick_urls()
    if not targets:
        print("Brak ofert do apply.")
        return

    svc = ApplyService()
    outcomes: list[dict] = []

    for i, row in enumerate(targets, 1):
        url = row["url"]
        print(f"[{i}/{len(targets)}] Apply {row.get('title', url)[:55]}...")
        try:
            resp = await svc.run(
                ApplyRequest(url=url, proceed=True, compile_pdf=True),
            )
            mark_evaluated(url)
            outcomes.append(
                {
                    "url": url,
                    "title": row.get("title"),
                    "company": row.get("company"),
                    "run_id": resp.run_id,
                    "stage": resp.stage,
                    "files": resp.files,
                    "pdf_files": resp.pdf_files,
                    "warnings": resp.warnings,
                    "message": resp.message,
                }
            )
            print(f"  -> files: {resp.files}")
        except Exception as exc:
            outcomes.append({"url": url, "error": str(exc)})
            print(f"  -> ERROR: {exc}")

    APPLY_PATH.write_text(json.dumps(outcomes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {APPLY_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
