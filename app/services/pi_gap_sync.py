"""Collect Pi-scored offers missing from Bielik inbox and import them."""

from __future__ import annotations

import csv
import io
import json
import re
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from app.models.jobs import SeenJobEntry
from app.storage.files import seen_key, today_iso
from app.storage.job_repository import JobRepository

SSH_HOST = "admin@192.168.0.194"
REMOTE_CSV = {
    "job_finder": "/home/admin/job_finder/out/report.csv",
    "my_resume": "/home/admin/My resume/out_fullrun/report.csv",
    "my_resume_rag": "/home/admin/my_resume_rag/out_rag_fullrun/report.csv",
}
REMOTE_TRACKER = "/home/admin/my_resume_rag/out_rag_fullrun/job_search_tracker.csv"

JOB_URL_RE = re.compile(
    r"(https?://(?:www\.)?(?:"
    r"pracuj\.pl/praca/[^\"\s\]]+|"
    r"pl\.linkedin\.com/jobs/view/[^\"\s\]]+|"
    r"justjoin\.it/job-offer/[^\"\s\]]+|"
    r"www\.praca\.pl/[^\"\s\]]+|"
    r"nofluffjobs\.com/pl/job/[^\"\s\]]+|"
    r"rocketjobs\.pl/oferta/[^\"\s\]]+|"
    r"theprotocol\.it/oferta-pracy/[^\"\s\]]+"
    r"))",
    re.I,
)
LOG_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


@dataclass
class PiJob:
    url: str
    title: str
    company: str
    score: int | None
    verdict: str
    apps: str
    portal: str


def norm_url(url: str) -> str:
    if not url:
        return ""
    u = url.strip().rstrip("/").lower()
    u = re.sub(r"\?.*", "", u)
    u = re.sub(r"#.*", "", u)
    u = u.replace("www.", "")
    m = re.search(r"jobs/view/[^/]+-at-[^/]+-(\d+)", u)
    if m:
        return f"linkedin:{m.group(1)}"
    m = re.search(r"oferta,(\d+)", u)
    if m:
        return f"pracuj:{m.group(1)}"
    m = re.search(r"_(\d+)\.html", u)
    if m:
        return f"praca-pl:{m.group(1)}"
    m = re.search(r"job-offer/([^/]+)", u)
    if m:
        return f"justjoin:{m.group(1)}"
    m = re.search(r"/oferta-pracy/([^/]+)", u)
    if m:
        return f"rocketjobs:{m.group(1)}"
    m = re.search(r"indeed\.com/rc/clk\?jk=([^&]+)", u)
    if m:
        return f"indeed:{m.group(1)}"
    return u


def portal_from_url(url: str) -> str:
    u = norm_url(url)
    raw = url.lower()
    if u.startswith("justjoin:") or "justjoin" in raw:
        return "justjoin"
    if "nofluffjobs" in raw:
        return "nofluffjobs"
    if u.startswith("rocketjobs:") or "rocketjobs" in raw:
        return "rocketjobs"
    if "theprotocol" in raw:
        return "theprotocol"
    if u.startswith("pracuj:") or "pracuj.pl" in raw:
        return "pracuj"
    if u.startswith("praca-pl:") or "praca.pl" in raw:
        return "praca-pl"
    if u.startswith("linkedin:") or "linkedin" in raw:
        return "linkedin-pl"
    return "other"


def ssh_cat(remote_path: str) -> str:
    result = subprocess.run(
        ["ssh", SSH_HOST, f"cat {remote_path!r}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def load_report_csv(text: str) -> dict[str, PiJob]:
    out: dict[str, PiJob] = {}
    for row in csv.DictReader(io.StringIO(text)):
        raw_url = row.get("URL", "")
        key = norm_url(raw_url)
        if not key:
            continue
        score_raw = row.get("Score", "")
        score = int(score_raw) if score_raw.isdigit() else None
        out[key] = PiJob(
            url=raw_url,
            title=row.get("Title") or "",
            company=row.get("Company") or "",
            score=score,
            verdict=row.get("Verdict") or "",
            apps="",
            portal=portal_from_url(raw_url),
        )
    return out


def _urls_from_log(text: str, cutoff: datetime, scored_keys: set[str]) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        m = LOG_TS_RE.match(line)
        if not m:
            continue
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        if ts < cutoff:
            continue
        for url in JOB_URL_RE.findall(line):
            key = norm_url(url)
            if key in scored_keys:
                found.add(key)
    return found


def collect_pi_jobs_48h(
    hours: int = 48,
    *,
    use_ssh: bool = True,
    cache_dir: Path | None = None,
) -> dict[str, PiJob]:
    """Return Pi jobs seen in logs/tracker within the last `hours`, enriched from report.csv."""
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_date = cutoff.date().isoformat()
    cache = cache_dir or Path("data/comparison_cache")

    reports: dict[str, dict[str, PiJob]] = {}
    for app, remote_path in REMOTE_CSV.items():
        cache_file = cache / f"{app}_report.csv"
        if use_ssh:
            text = ssh_cat(remote_path)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(text, encoding="utf-8")
        elif cache_file.exists():
            text = cache_file.read_text(encoding="utf-8")
        else:
            raise FileNotFoundError(f"Missing cache: {cache_file} (use SSH or prefetch)")
        reports[app] = load_report_csv(text)

    scored_keys = set().union(*(r.keys() for r in reports.values()))
    urls_by_app: dict[str, set[str]] = defaultdict(set)

    tracker_path = cache / "my_resume_rag_tracker.csv"
    if use_ssh:
        tracker_text = ssh_cat(REMOTE_TRACKER)
        tracker_path.write_text(tracker_text, encoding="utf-8")
    elif tracker_path.exists():
        tracker_text = tracker_path.read_text(encoding="utf-8")
    else:
        tracker_text = ""

    for row in csv.DictReader(io.StringIO(tracker_text)):
        if (row.get("date") or "") < cutoff_date:
            continue
        key = norm_url(row.get("url", ""))
        if key:
            urls_by_app["my_resume_rag"].add(key)

    log_specs = [
        ("job_finder", "strings ~/job_finder/logs/job_finder.log"),
        ("my_resume", "strings ~/My\\ resume/logs/job_agent.log"),
    ]
    for app, cmd in log_specs:
        if use_ssh:
            text = subprocess.run(
                ["ssh", SSH_HOST, cmd],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        else:
            log_file = cache / f"{app}_agent.log"
            text = log_file.read_text(encoding="utf-8") if log_file.exists() else ""
        urls_by_app[app] |= _urls_from_log(text, cutoff, scored_keys)

    merged: dict[str, PiJob] = {}
    all_urls = set().union(*urls_by_app.values()) if urls_by_app else set()
    for key in all_urls:
        job: PiJob | None = None
        apps: list[str] = []
        for app, jobs in reports.items():
            if key in jobs:
                apps.append(app)
                if job is None or (jobs[key].score or 0) > (job.score or 0):
                    job = jobs[key]
        if job is None:
            continue
        merged[key] = PiJob(
            url=job.url,
            title=job.title,
            company=job.company,
            score=job.score,
            verdict=job.verdict,
            apps=",".join(apps),
            portal=job.portal,
        )
    return merged


def load_worksphere_url_keys(seen_path: Path) -> set[str]:
    data = json.loads(seen_path.read_text(encoding="utf-8"))
    return {norm_url(v.get("url") or k) for k, v in data.get("seen", {}).items()}


def pi_jobs_missing_from_worksphere(
    pi_jobs: dict[str, PiJob],
    worksphere_keys: set[str],
) -> list[PiJob]:
    return [j for k, j in pi_jobs.items() if k not in worksphere_keys]


def is_importable(job: PiJob, *, min_score: int, import_all: bool) -> bool:
    if import_all:
        return True
    if job.verdict == "✅":
        return True
    if job.verdict == "🟨" and job.score is not None and job.score >= min_score:
        return True
    return False


def map_pi_fit(job: PiJob) -> Literal["high", "medium", "low"]:
    if job.verdict == "✅":
        return "high"
    if job.verdict == "🟨" and job.score is not None and job.score >= 72:
        return "medium"
    return "low"


def import_pi_gaps(
    jobs: list[PiJob],
    seen_path: Path,
    *,
    dry_run: bool = False,
) -> int:
    repo = JobRepository(seen_path)
    existing = {norm_url(v.url) for v in repo.all().values()}
    imported = 0
    for job in jobs:
        key_url = norm_url(job.url)
        if key_url in existing:
            continue
        entry = SeenJobEntry(
            title=job.title,
            company=job.company,
            url=job.url,
            first_seen=today_iso(),
            fit=map_pi_fit(job),
            status="new",
            portal=job.portal,
            import_source="pi_import",
            pi_score=job.score,
            pi_verdict=job.verdict,
            pi_app=job.apps,
        )
        if not dry_run:
            repo.upsert(seen_key(job.url, job.company, job.title), entry)
        imported += 1
    if not dry_run and imported:
        repo.flush()
    return imported


def sync_pi_metadata(
    jobs_by_url: dict[str, PiJob],
    seen_path: Path,
    *,
    dry_run: bool = False,
) -> int:
    """Update pi_score/pi_verdict/pi_app on existing seen_jobs entries."""
    repo = JobRepository(seen_path)
    updated = 0
    for key, entry in repo.all().items():
        url_key = norm_url(entry.url or key)
        job = jobs_by_url.get(url_key)
        if not job:
            continue
        changes = {}
        if job.score is not None and job.score != entry.pi_score:
            changes["pi_score"] = job.score
        if job.verdict and job.verdict != entry.pi_verdict:
            changes["pi_verdict"] = job.verdict
        if job.apps and job.apps != entry.pi_app:
            changes["pi_app"] = job.apps
        if not changes:
            continue
        if not dry_run:
            repo.upsert(key, entry.model_copy(update=changes))
        updated += 1
    if not dry_run and updated:
        repo.flush()
    return updated


def mark_only_worksphere_deep_eval(
    worksphere_today_urls: set[str],
    remote_any_urls: set[str],
    seen_path: Path,
    *,
    dry_run: bool = False,
) -> int:
    """Flag WorkSphere-only offers for deep evaluation queue."""
    only_worksphere = worksphere_today_urls - remote_any_urls
    if not only_worksphere:
        return 0
    repo = JobRepository(seen_path)
    marked = 0
    for key, entry in repo.all().items():
        url_key = norm_url(entry.url or key)
        if url_key not in only_worksphere:
            continue
        if entry.needs_deep_eval:
            continue
        if not dry_run:
            repo.upsert(key, entry.model_copy(update={"needs_deep_eval": True}))
        marked += 1
    if not dry_run and marked:
        repo.flush()
    return marked


def coverage_summary(
    pi_jobs: dict[str, PiJob],
    worksphere_keys: set[str],
    *,
    hours: int,
) -> dict:
    missing = pi_jobs_missing_from_worksphere(pi_jobs, worksphere_keys)
    overlap = len(pi_jobs) - len(missing)
    pi_total = len(pi_jobs)
    pct = round(100 * overlap / pi_total, 1) if pi_total else 0.0
    return {
        "generated_at": datetime.now().isoformat(),
        "hours": hours,
        "pi_scored_48h": pi_total,
        "overlap_with_worksphere": overlap,
        "overlap_pct": pct,
        "pi_only": len(missing),
        "worksphere_inbox_total": len(worksphere_keys),
    }
