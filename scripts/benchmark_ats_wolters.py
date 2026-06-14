#!/usr/bin/env python3
"""Run draft retry for Wolters #41 and save ATS checklist metrics (A/B model comparison)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.services.pipeline_service import PipelineService  # noqa: E402

APP_ID = 41


async def run_draft(model_label: str) -> dict:
    svc = PipelineService()
    t0 = time.perf_counter()
    resp = await svc.retry_stage(APP_ID, "draft", compile_pdf=True)
    elapsed = round(time.perf_counter() - t0, 1)
    ver = resp.verification or {}
    cov = ver.get("keyword_coverage") or {}
    bullets = []
    for item in ver.get("items") or []:
        if item.get("label", "").startswith("Bullet quality"):
            note = item.get("note", "")
            if "%" in note:
                bullets.append(note)
    row = {
        "model_label": model_label,
        "date": date.today().isoformat(),
        "draft_seconds": elapsed,
        "ats_score": ver.get("ats_score"),
        "checklist_passed": ver.get("passed"),
        "checklist_total": ver.get("total"),
        "all_pass": ver.get("all_pass"),
        "keyword_coverage_ratio": cov.get("coverage_ratio"),
        "missing_keywords": cov.get("missing_keywords"),
        "truth_violations": ver.get("truth_violations"),
        "bullet_quality_note": bullets[0] if bullets else None,
        "ats_items": [
            {"label": i.get("label"), "pass": i.get("pass"), "note": i.get("note")}
            for i in (ver.get("items") or [])
            if i.get("category") == "ats"
        ],
    }
    out_dir = ROOT / "data" / "llm_benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = model_label.lower().replace(" ", "_").replace("/", "_")
    path = out_dir / f"ats_wolters_{slug}_{date.today().isoformat()}.json"
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(row, ensure_ascii=False, indent=2))
    print(f"Saved: {path}")
    return row


def compare_reports(paths: list[Path]) -> None:
    """Print side-by-side ATS metrics from saved benchmark JSON files."""
    rows: list[dict] = []
    for path in paths:
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    if len(rows) < 2:
        raise SystemExit("Provide at least two --compare JSON result files")

    headers = [
        "model_label",
        "draft_seconds",
        "ats_score",
        "checklist_passed",
        "checklist_total",
        "keyword_coverage_ratio",
        "bullet_quality_note",
    ]
    print("| Metric | " + " | ".join(r.get("model_label", "?") for r in rows) + " |")
    print("| --- | " + " | ".join("---" for _ in rows) + " |")
    for key in headers:
        print("| " + key + " | " + " | ".join(str(r.get(key, "")) for r in rows) + " |")


def main() -> None:
    parser = argparse.ArgumentParser(description="ATS benchmark for Wolters application #41")
    parser.add_argument(
        "--model-label",
        default=get_settings().llm_model,
        help="Label for report (current LLM model name)",
    )
    parser.add_argument(
        "--compare",
        nargs="+",
        type=Path,
        help="Compare two or more saved ats_wolters_*.json reports (no draft run)",
    )
    args = parser.parse_args()
    if args.compare:
        compare_reports(args.compare)
        return
    asyncio.run(run_draft(args.model_label))


if __name__ == "__main__":
    main()
