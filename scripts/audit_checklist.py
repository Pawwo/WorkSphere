#!/usr/bin/env python3
"""Audit verification checklist results across all applications."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.models.apply import FitEvaluation, JobParsed, ReviewerResult  # noqa: E402
from app.services.pipeline_service import PipelineService  # noqa: E402
from app.services.verification_service import run_verification_checklist  # noqa: E402
from app.storage.db import Database  # noqa: E402


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def audit_applications(*, apps_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        ver_path = app_dir / "verification.json"
        if not ver_path.exists():
            continue
        ver = _load_json(ver_path)
        parsed = _load_json(app_dir / "parsed.json")
        draft = _load_json(app_dir / "draft.json")
        failed = [
            i.get("label", "")
            for i in (ver.get("items") or [])
            if not i.get("pass")
        ]
        decisions = draft.get("tailoring_decisions") or []
        rows.append(
            {
                "slug": app_dir.name,
                "passed": ver.get("passed"),
                "total": ver.get("total"),
                "all_pass": ver.get("all_pass"),
                "failed_labels": failed,
                "tailoring_note": decisions[0] if decisions else "",
                "language": parsed.get("language"),
                "raw_len": len(parsed.get("raw_text") or ""),
            }
        )
    return rows


def print_report(rows: list[dict]) -> int:
    failing = [r for r in rows if not r.get("all_pass")]
    print(f"Applications with verification.json: {len(rows)}")
    print(f"Full pass: {len(rows) - len(failing)} | Partial fail: {len(failing)}")
    print()
    for r in rows:
        status = "PASS" if r.get("all_pass") else "FAIL"
        print(
            f"[{status}] {r['slug']}: {r.get('passed')}/{r.get('total')} "
            f"lang={r.get('language')} raw_len={r.get('raw_len')}"
        )
        if r.get("failed_labels"):
            print(f"       failed: {', '.join(r['failed_labels'])}")
        if r.get("tailoring_note"):
            print(f"       tailor: {r['tailoring_note'][:120]}")
    return len(failing)


def recheck_applications(*, apps_dir: Path, repo_root: Path) -> None:
    """Re-run verification checklist from on-disk artifacts (no LLM)."""
    profile_md = (repo_root / "data/profile/01-candidate-profile.md").read_text(encoding="utf-8")
    for app_dir in sorted(apps_dir.iterdir()):
        if not app_dir.is_dir():
            continue
        parsed_data = _load_json(app_dir / "parsed.json")
        if not parsed_data:
            continue
        job = JobParsed(**parsed_data)
        draft = _load_json(app_dir / "draft.json")
        eval_data = _load_json(app_dir / "evaluation.json")
        if not eval_data:
            eval_data = {"overall_fit": "moderate", "recommendation": ""}

        cv_rel = draft.get("cv_file")
        cover_rel = draft.get("cover_file")
        if not cv_rel:
            print(f"SKIP {app_dir.name}: brak cv_file w draft.json")
            continue
        cv_path = repo_root / cv_rel
        cover_path = repo_root / cover_rel if cover_rel else None
        if not cv_path.exists():
            print(f"SKIP {app_dir.name}: brak pliku {cv_rel}")
            continue

        renderer = "latex" if cv_path.suffix.lower() == ".tex" else "html"
        cv_content = cv_path.read_text(encoding="utf-8")
        cover_content = ""
        if cover_path and cover_path.exists():
            if cover_path.suffix.lower() == ".tex":
                cover_content = cover_path.read_text(encoding="utf-8")
            else:
                cover_content = cover_path.read_text(encoding="utf-8")
        elif cover_rel and cover_rel.endswith(".tex"):
            legacy = repo_root / cover_rel
            if legacy.exists():
                cover_content = legacy.read_text(encoding="utf-8")
                renderer = "latex"

        pdf_files: list[str] = []
        cv_pdf = cv_path.with_suffix(".pdf")
        if cv_pdf.exists():
            pdf_files.append(str(cv_pdf))
        if cover_path:
            cover_pdf = cover_path.with_suffix(".pdf")
            if cover_pdf.exists():
                pdf_files.append(str(cover_pdf))

        ver = run_verification_checklist(
            job=job,
            cv_tex=cv_content,
            cover_tex=cover_content,
            profile_md=profile_md,
            evaluation=FitEvaluation(**eval_data),
            reviewer=ReviewerResult(**_load_json(app_dir / "reviewer.json") or {}),
            pdf_files=pdf_files,
            pdf_checks=[f"pass: {Path(p).name}" for p in pdf_files] if pdf_files else [],
            renderer=renderer,
            job_targets=draft.get("job_targets") or {},
            tailoring_decisions=draft.get("tailoring_decisions") or [],
        )
        (app_dir / "verification.json").write_text(
            json.dumps(ver, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"Recheck {app_dir.name}: {ver.get('passed')}/{ver.get('total')} "
            f"all_pass={ver.get('all_pass')}"
        )


async def _slug_to_app_id(db: Database) -> dict[str, int]:
    mapping: dict[str, int] = {}
    apps = await db.list_applications(limit=500)
    for row in apps:
        slug = row.get("company_slug") or ""
        if slug and row.get("id"):
            mapping[slug] = int(row["id"])
    return mapping


async def retry_failing(
    rows: list[dict],
    *,
    stages: list[str],
    compile_pdf: bool,
) -> None:
    failing = [r for r in rows if not r.get("all_pass")]
    if not failing:
        print("No failing applications to retry.")
        return
    db = Database(get_settings().db_path)
    slug_map = await _slug_to_app_id(db)
    svc = PipelineService()
    for r in failing:
        slug = r["slug"]
        app_id = slug_map.get(slug)
        if not app_id:
            print(f"SKIP {slug}: brak application_id w bazie")
            continue
        for stage in stages:
            print(f"Retry {slug} (#{app_id}) stage={stage} …", flush=True)
            try:
                resp = await svc.retry_stage(app_id, stage, compile_pdf=compile_pdf)
                ver = resp.verification or {}
                print(
                    f"  → {ver.get('passed')}/{ver.get('total')} "
                    f"all_pass={ver.get('all_pass')}",
                    flush=True,
                )
            except Exception as exc:
                print(f"  ERROR: {exc}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit application verification checklists")
    parser.add_argument(
        "--recheck",
        action="store_true",
        help="Recompute verification.json from stored CV/cover (no LLM)",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Re-run pipeline stages for applications with checklist failures",
    )
    parser.add_argument(
        "--stages",
        default="parse,draft,checklist",
        help="Comma-separated stages for --retry (default: parse,draft,checklist)",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Skip PDF compilation during retry",
    )
    args = parser.parse_args()
    settings = get_settings()
    apps_dir = settings.data_dir / "applications"
    rows = audit_applications(apps_dir=apps_dir)
    if args.recheck:
        recheck_applications(apps_dir=apps_dir, repo_root=settings.repo_root)
        rows = audit_applications(apps_dir=apps_dir)
    fail_count = print_report(rows)
    if args.retry and fail_count:
        stages = [s.strip() for s in args.stages.split(",") if s.strip()]
        asyncio.run(
            retry_failing(rows, stages=stages, compile_pdf=not args.no_pdf)
        )
        rows = audit_applications(apps_dir=apps_dir)
        print("\n--- After retry ---")
        print_report(rows)
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
