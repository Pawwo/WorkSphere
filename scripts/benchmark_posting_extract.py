#!/usr/bin/env python3
"""Compare current seen_jobs.description vs extract_key_description against apply full text.

Usage:
  uv run python scripts/benchmark_posting_extract.py --limit 100 --multi-portal
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.models.jobs import SeenJobEntry
from app.services.inbox.language_triage import fetch_posting_text_sync, job_posting_blob
from app.services.job_fetcher import fetch_job_posting
from app.services.scrape.posting_extract import extract_key_description
from app.storage.files import is_http_url
from app.storage.job_repository import JobRepository

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

PORTAL_QUOTAS_100: dict[str, int] = {
    "linkedin-pl": 40,
    "pracuj": 29,
    "praca-pl": 24,
    "justjoin": 6,
    "rocketjobs": 1,
}


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (text or "").lower())}


def _metrics(hypothesis: str, reference: str) -> dict[str, float]:
    ref = _tokenize(reference)
    hyp = _tokenize(hypothesis)
    if not ref or not hyp:
        return {"recall": 0.0, "precision": 0.0, "f1": 0.0}
    inter = hyp & ref
    recall = len(inter) / len(ref)
    precision = len(inter) / len(hyp)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"recall": recall, "precision": precision, "f1": f1}


def _noise_vs_gt(hypothesis: str, requirements_gt: str) -> float:
    hyp = _tokenize(hypothesis)
    gt = _tokenize(requirements_gt)
    if not hyp:
        return 1.0
    if not gt:
        return 0.0
    return len(hyp - gt) / len(hyp)


def _portal_name(job: SeenJobEntry, url: str) -> str:
    p = (job.portal or "").lower().strip()
    if p:
        return p
    u = url.lower()
    if "linkedin" in u:
        return "linkedin-pl"
    if "pracuj.pl" in u:
        return "pracuj"
    if "praca.pl" in u:
        return "praca-pl"
    if "justjoin" in u:
        return "justjoin"
    if "rocketjobs" in u:
        return "rocketjobs"
    return "other"


def _job_sort_key(item: tuple[str, SeenJobEntry]) -> tuple[int, int, str]:
    _url, job = item
    status_rank = {"new": 0, "evaluated": 1, "skipped": 2}.get(job.status, 3)
    desc_len = len(job.description or "")
    return (status_rank, -desc_len, job.first_seen or "")


async def _apply_full_text(url: str) -> str:
    parsed = await fetch_job_posting(url=url)
    return parsed.raw_text or ""


def _triage_baseline_text(job: SeenJobEntry, url: str) -> tuple[str, str]:
    current_desc = (job.description or "").strip()
    fetched_raw = fetch_posting_text_sync(url) or ""
    triage_blob = job_posting_blob(job)
    if fetched_raw and len(triage_blob) < 80:
        triage_blob = f"{triage_blob} {fetched_raw}".strip()
    return current_desc, triage_blob


@dataclass
class Row:
    url: str
    title: str
    portal: str
    status: str
    current_desc_len: int
    triage_blob_len: int
    apply_full_len: int
    extracted_len: int
    requirements_gt_len: int
    current_vs_apply: dict
    triage_blob_vs_apply: dict
    extracted_vs_apply: dict
    current_vs_req_gt: dict
    extracted_vs_req_gt: dict
    current_noise: float
    extracted_noise: float
    extracted_wins: bool
    error: str | None = None


def _select_jobs_linkedin_only(limit: int) -> list[tuple[str, SeenJobEntry]]:
    repo = JobRepository(get_settings().seen_jobs_path)
    seen = repo.all()
    primary: list[tuple[str, SeenJobEntry]] = []
    fallback: list[tuple[str, SeenJobEntry]] = []
    for key, job in seen.items():
        url = job.url or key
        if not is_http_url(url) or "linkedin" not in url.lower():
            continue
        if job.status in ("new", "evaluated"):
            primary.append((url, job))
        else:
            fallback.append((url, job))
    primary.sort(key=_job_sort_key)
    fallback.sort(key=_job_sort_key)
    rows = primary[:limit]
    if len(rows) < limit:
        rows.extend(fallback[: limit - len(rows)])
    return rows[:limit]


def _select_jobs_multi_portal(limit: int) -> list[tuple[str, SeenJobEntry]]:
    repo = JobRepository(get_settings().seen_jobs_path)
    seen = repo.all()
    by_portal: dict[str, list[tuple[str, SeenJobEntry]]] = defaultdict(list)
    for key, job in seen.items():
        url = job.url or key
        if not is_http_url(url):
            continue
        by_portal[_portal_name(job, url)].append((url, job))

    for portal in by_portal:
        by_portal[portal].sort(key=_job_sort_key)

    if limit >= 100:
        quotas = dict(PORTAL_QUOTAS_100)
    else:
        portals = sorted(by_portal.keys(), key=lambda p: -len(by_portal[p]))
        per = max(1, limit // max(len(portals), 1))
        quotas = {p: per for p in portals}

    selected: list[tuple[str, SeenJobEntry]] = []
    used_urls: set[str] = set()

    for portal, quota in quotas.items():
        pool = by_portal.get(portal, [])
        for url, job in pool:
            if url in used_urls:
                continue
            selected.append((url, job))
            used_urls.add(url)
            if len([s for s in selected if _portal_name(s[1], s[0]) == portal]) >= quota:
                break

    if len(selected) < limit:
        rest = []
        for portal, pool in sorted(by_portal.items(), key=lambda x: -len(x[1])):
            for url, job in pool:
                if url not in used_urls:
                    rest.append((url, job))
        rest.sort(key=_job_sort_key)
        selected.extend(rest[: limit - len(selected)])

    return selected[:limit]


def _portal_summary(rows: list[Row]) -> dict:
    by_p: dict[str, list[Row]] = defaultdict(list)
    for r in rows:
        if r.error:
            continue
        by_p[r.portal].append(r)

    out = {}
    for portal, items in sorted(by_p.items()):
        n = len(items)
        if not n:
            continue
        out[portal] = {
            "count": n,
            "avg_current_noise": round(sum(i.current_noise for i in items) / n, 4),
            "avg_extracted_noise": round(sum(i.extracted_noise for i in items) / n, 4),
            "avg_current_req_precision": round(
                sum(i.current_vs_req_gt["precision"] for i in items) / n, 4
            ),
            "avg_extracted_req_precision": round(
                sum(i.extracted_vs_req_gt["precision"] for i in items) / n, 4
            ),
            "extracted_wins": sum(1 for i in items if i.extracted_wins),
        }
    return out


async def run_benchmark(limit: int, *, multi_portal: bool) -> dict:
    jobs = _select_jobs_multi_portal(limit) if multi_portal else _select_jobs_linkedin_only(limit)
    rows_data: list[Row] = []

    for i, (url, job) in enumerate(jobs, 1):
        portal = _portal_name(job, url)
        log.info("[%d/%d] %s — %s", i, len(jobs), portal, job.title[:60])
        try:
            apply_full = await _apply_full_text(url)
            fetch_strip = fetch_posting_text_sync(url) or apply_full
            requirements_gt = extract_key_description(
                fetch_strip, portal=portal, url=url
            )
            current_desc, triage_blob = _triage_baseline_text(job, url)
            extracted = extract_key_description(fetch_strip, portal=portal, url=url)

            c_apply = _metrics(current_desc, apply_full)
            t_apply = _metrics(triage_blob, apply_full)
            e_apply = _metrics(extracted, apply_full)
            c_gt = _metrics(current_desc, requirements_gt) if requirements_gt else {
                "recall": 0.0, "precision": 0.0, "f1": 0.0
            }
            e_gt = _metrics(extracted, requirements_gt) if requirements_gt else {
                "recall": 0.0, "precision": 0.0, "f1": 0.0
            }
            c_noise = _noise_vs_gt(current_desc, requirements_gt)
            e_noise = _noise_vs_gt(extracted, requirements_gt)
            wins = (
                e_gt["f1"] > c_gt["f1"] + 0.02
                or (e_noise < c_noise - 0.05 and e_gt["recall"] >= c_gt["recall"] - 0.05)
            )
            rows_data.append(
                Row(
                    url=url,
                    title=job.title,
                    portal=portal,
                    status=job.status,
                    current_desc_len=len(current_desc),
                    triage_blob_len=len(triage_blob),
                    apply_full_len=len(apply_full),
                    extracted_len=len(extracted),
                    requirements_gt_len=len(requirements_gt),
                    current_vs_apply={k: round(v, 4) for k, v in c_apply.items()},
                    triage_blob_vs_apply={k: round(v, 4) for k, v in t_apply.items()},
                    extracted_vs_apply={k: round(v, 4) for k, v in e_apply.items()},
                    current_vs_req_gt={k: round(v, 4) for k, v in c_gt.items()},
                    extracted_vs_req_gt={k: round(v, 4) for k, v in e_gt.items()},
                    current_noise=round(c_noise, 4),
                    extracted_noise=round(e_noise, 4),
                    extracted_wins=wins,
                )
            )
        except Exception as exc:
            log.warning("  FAILED: %s", exc)
            rows_data.append(
                Row(
                    url=url,
                    title=job.title,
                    portal=portal,
                    status=job.status,
                    current_desc_len=0,
                    triage_blob_len=0,
                    apply_full_len=0,
                    extracted_len=0,
                    requirements_gt_len=0,
                    current_vs_apply={"recall": 0, "precision": 0, "f1": 0},
                    triage_blob_vs_apply={"recall": 0, "precision": 0, "f1": 0},
                    extracted_vs_apply={"recall": 0, "precision": 0, "f1": 0},
                    current_vs_req_gt={"recall": 0, "precision": 0, "f1": 0},
                    extracted_vs_req_gt={"recall": 0, "precision": 0, "f1": 0},
                    current_noise=1.0,
                    extracted_noise=1.0,
                    extracted_wins=False,
                    error=str(exc),
                )
            )

    ok = [r for r in rows_data if not r.error]
    n = len(ok)

    def avg(getter) -> float:
        return sum(getter(r) for r in ok) / n if n else 0.0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(rows_data),
        "count_ok": n,
        "count_errors": len(rows_data) - n,
        "multi_portal": multi_portal,
        "portals_sampled": dict(sorted(
            {p: sum(1 for r in rows_data if r.portal == p and not r.error) for p in {r.portal for r in rows_data}}.items(),
            key=lambda x: -x[1],
        )),
        "methodology": {
            "apply_reference": "fetch_job_posting(url) -> raw_text",
            "baseline_current": "seen_jobs.description",
            "new_method": "extract_key_description(fetch_posting_text_sync)",
            "requirements_gt": "extract_key_description on fetch strip",
        },
        "avg_current_vs_apply_f1": round(avg(lambda r: r.current_vs_apply["f1"]), 4),
        "avg_extracted_vs_apply_f1": round(avg(lambda r: r.extracted_vs_apply["f1"]), 4),
        "avg_current_vs_req_gt_recall": round(avg(lambda r: r.current_vs_req_gt["recall"]), 4),
        "avg_extracted_vs_req_gt_recall": round(avg(lambda r: r.extracted_vs_req_gt["recall"]), 4),
        "avg_current_vs_req_gt_precision": round(avg(lambda r: r.current_vs_req_gt["precision"]), 4),
        "avg_extracted_vs_req_gt_precision": round(avg(lambda r: r.extracted_vs_req_gt["precision"]), 4),
        "avg_current_noise": round(avg(lambda r: r.current_noise), 4),
        "avg_extracted_noise": round(avg(lambda r: r.extracted_noise), 4),
        "extracted_wins_count": sum(1 for r in ok if r.extracted_wins),
        "by_portal": _portal_summary(rows_data),
        "rows": [asdict(r) for r in rows_data],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--multi-portal", action="store_true", help="Sample across job portals")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    multi = args.multi_portal or args.limit >= 50

    settings = get_settings()
    out = args.out or (
        settings.data_dir
        / "benchmarks"
        / f"posting_extract_{'multi' if multi else 'linkedin'}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)

    summary = asyncio.run(run_benchmark(args.limit, multi_portal=multi))
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nJobs benchmarked: {summary['count']} (ok={summary['count_ok']}, errors={summary['count_errors']})")
    print(f"Portals: {summary['portals_sampled']}")
    print(f"  current vs req-GT precision:  {summary['avg_current_vs_req_gt_precision']:.3f}")
    print(f"  extracted vs req-GT precision:{summary['avg_extracted_vs_req_gt_precision']:.3f}")
    print(f"  current noise:   {summary['avg_current_noise']:.3f}")
    print(f"  extracted noise: {summary['avg_extracted_noise']:.3f}")
    print(f"  extracted wins: {summary['extracted_wins_count']}/{summary['count_ok']}")
    print("By portal:")
    for portal, stats in summary.get("by_portal", {}).items():
        print(
            f"  {portal}: n={stats['count']} wins={stats['extracted_wins']}/{stats['count']} "
            f"noise {stats['avg_current_noise']:.2f}->{stats['avg_extracted_noise']:.2f} "
            f"prec {stats['avg_current_req_precision']:.2f}->{stats['avg_extracted_req_precision']:.2f}"
        )
    print(f"Written: {out}")


if __name__ == "__main__":
    main()
