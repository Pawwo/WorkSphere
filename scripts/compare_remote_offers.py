#!/usr/bin/env python3
"""Compare Pi job apps (job_finder, My resume, my_resume_rag) vs WorkSphere."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.pi_gap_sync import (  # noqa: E402
    collect_pi_jobs_48h,
    coverage_summary,
    import_pi_gaps,
    is_importable,
    load_worksphere_url_keys,
    mark_only_worksphere_deep_eval,
    norm_url,
    pi_jobs_missing_from_worksphere,
    sync_pi_metadata,
)
DEFAULT_SEEN = ROOT / "data" / "job_scraper" / "seen_jobs.json"
DEFAULT_CACHE = ROOT / "data" / "comparison_cache"
DEFAULT_OUTPUT = ROOT / "docs" / "comparison-{date}.md"

SSH_HOST = "admin@192.168.0.194"
REMOTE_CSV = {
    "job_finder": "/home/admin/job_finder/out/report.csv",
    "my_resume": "/home/admin/My resume/out_fullrun/report.csv",
    "my_resume_rag": "/home/admin/my_resume_rag/out_rag_fullrun/report.csv",
}


@dataclass
class RemoteJob:
    score: int | None
    verdict: str
    title: str
    company: str
    url: str


@dataclass
class WorkSphereJob:
    fit: str
    title: str
    company: str
    portal: str
    url: str
    status: str


@dataclass
class ComparisonResult:
    compare_date: str
    worksphere_today: dict[str, WorkSphereJob]
    worksphere_all_count: int
    remote: dict[str, dict[str, RemoteJob]]
    overlap_by_app: dict[str, set[str]] = field(default_factory=dict)
    any_remote: set[str] = field(default_factory=set)
    only_worksphere: set[str] = field(default_factory=set)
    cross_tabs: dict[str, Counter[tuple[str, str]]] = field(default_factory=dict)
    delta_mode: bool = False
    remote_delta: dict[str, dict[str, RemoteJob]] = field(default_factory=dict)


def load_worksphere(path: Path, compare_date: str) -> tuple[dict[str, WorkSphereJob], int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    seen = data.get("seen", {})
    today: dict[str, WorkSphereJob] = {}
    for key, entry in seen.items():
        if entry.get("first_seen") != compare_date:
            continue
        url = norm_url(entry.get("url") or key)
        today[url] = WorkSphereJob(
            fit=entry.get("fit") or "medium",
            title=entry.get("title") or "",
            company=entry.get("company") or "",
            portal=entry.get("portal") or "",
            url=entry.get("url") or key,
            status=entry.get("status") or "new",
        )
    return today, len(seen)


def ssh_cat(remote_path: str) -> str:
    result = subprocess.run(
        ["ssh", SSH_HOST, f"cat {remote_path!r}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def load_remote_csv(text: str) -> dict[str, RemoteJob]:
    out: dict[str, RemoteJob] = {}
    for row in csv.DictReader(io.StringIO(text)):
        raw_url = row.get("URL", "")
        url = norm_url(raw_url)
        if not url:
            continue
        score_raw = row.get("Score", "")
        score = int(score_raw) if score_raw.isdigit() else None
        out[url] = RemoteJob(
            score=score,
            verdict=row.get("Verdict") or "",
            title=row.get("Title") or "",
            company=row.get("Company") or "",
            url=raw_url,
        )
    return out


def app_stats(jobs: dict[str, RemoteJob]) -> dict[str, Any]:
    verdicts = Counter(j.verdict for j in jobs.values())
    scores = [j.score for j in jobs.values() if j.score is not None]
    return {
        "total": len(jobs),
        "verdicts": dict(verdicts),
        "good": verdicts.get("✅", 0),
        "yellow": verdicts.get("🟨", 0),
        "red": verdicts.get("🟥", 0) + verdicts.get("❌", 0),
        "score_avg": round(sum(scores) / len(scores), 1) if scores else 0,
        "score_max": max(scores) if scores else 0,
    }


def _remote_delta(
    prev: dict[str, RemoteJob],
    current: dict[str, RemoteJob],
) -> dict[str, RemoteJob]:
    new_keys = set(current) - set(prev)
    return {k: current[k] for k in new_keys}


def build_comparison(
    compare_date: str,
    seen_path: Path,
    *,
    use_ssh: bool = True,
    local_csv: dict[str, Path] | None = None,
    delta: bool = False,
) -> ComparisonResult:
    worksphere_today, all_count = load_worksphere(seen_path, compare_date)
    remote: dict[str, dict[str, RemoteJob]] = {}
    remote_delta: dict[str, dict[str, RemoteJob]] = {}

    cache_dir = DEFAULT_CACHE
    for app, remote_path in REMOTE_CSV.items():
        cache_file = cache_dir / f"{app}_report.csv"
        prev: dict[str, RemoteJob] = {}
        if delta and cache_file.exists():
            prev = load_remote_csv(cache_file.read_text(encoding="utf-8"))
        if local_csv and app in local_csv:
            text = local_csv[app].read_text(encoding="utf-8")
        elif use_ssh:
            text = ssh_cat(remote_path)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(text, encoding="utf-8")
        elif cache_file.exists():
            text = cache_file.read_text(encoding="utf-8")
        else:
            raise ValueError(f"No data source for {app} (run without --no-ssh first)")
        current = load_remote_csv(text)
        remote[app] = current
        if delta:
            remote_delta[app] = _remote_delta(prev, current)

    compare_remote = remote_delta if delta else remote

    result = ComparisonResult(
        compare_date=compare_date,
        worksphere_today=worksphere_today,
        worksphere_all_count=all_count,
        remote=compare_remote,
        delta_mode=delta,
        remote_delta=remote_delta,
    )

    for app, jobs in compare_remote.items():
        overlap = set(worksphere_today) & set(jobs)
        result.overlap_by_app[app] = overlap
        result.cross_tabs[app] = Counter(
            (worksphere_today[u].fit, jobs[u].verdict) for u in overlap
        )

    result.any_remote = {u for u in worksphere_today if any(u in compare_remote[a] for a in compare_remote)}
    result.only_worksphere = set(worksphere_today) - result.any_remote
    return result


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    return "\n".join(lines)


def _escape_md(text: str, max_len: int = 55) -> str:
    t = text.replace("|", "\\|").replace("\n", " ")
    return t if len(t) <= max_len else t[: max_len - 1] + "…"


def _read_cache_log(cache_dir: Path, name: str) -> list[str]:
    path = cache_dir / name
    if not path.exists():
        return []
    return [ln.rstrip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def render_report(result: ComparisonResult, cache_dir: Path) -> str:
    d = result.compare_date
    ws = result.worksphere_today
    n = len(ws)
    fit_dist = Counter(j.fit for j in ws.values())
    portal_dist = Counter(j.portal for j in ws.values())

    lines: list[str] = [
        f"# Porównanie ofert: Pi vs WorkSphere ({d})",
        "",
        "Wygenerowano przez `scripts/compare_remote_offers.py`.",
        "",
        "## Metadane",
        "",
        f"- **Data porównania:** {d}",
        f"- **Host Pi:** `{SSH_HOST}` (hostname: Agent)",
        f"- **Źródło WorkSphere:** `data/job_scraper/seen_jobs.json` (`first_seen == {d}`)",
        "- **Źródła Pi:** `job_finder/out/report.csv`, `My resume/out_fullrun/report.csv`, `my_resume_rag/out_rag_fullrun/report.csv`",
        f"- **Tryb delta:** {'tak (nowe URL vs poprzedni cache)' if result.delta_mode else 'nie (kumulatywny report.csv)'}",
        "- **Klucz łączenia:** znormalizowany URL z ID portalowym (linkedin/pracuj/praca-pl/…)",
        "",
        "## Podsumowanie liczbowe",
        "",
        "### WorkSphere (oferty z dzisiejszego scrapingu)",
        "",
        f"- **Nowe dziś:** {n}",
        f"- **Inbox łącznie:** {result.worksphere_all_count}",
        f"- **Fit:** low {fit_dist.get('low', 0)}, medium {fit_dist.get('medium', 0)}, high {fit_dist.get('high', 0)}",
        f"- **Portale:** {', '.join(f'{p} {c}' for p, c in portal_dist.most_common())}",
        "",
        "### Aplikacje na Pi" + (" (delta dziś)" if result.delta_mode else " (kumulatywny scoring)"),
        "",
    ]

    stats_rows = []
    for app in ("job_finder", "my_resume", "my_resume_rag"):
        s = app_stats(result.remote[app])
        stats_rows.append([
            app,
            str(s["total"]),
            str(s["good"]),
            str(s["yellow"]),
            str(s["red"]),
            str(s["score_avg"]),
            str(s["score_max"]),
        ])
    lines.append(_md_table(
        ["Aplikacja", "Ofert", "✅", "🟨", "🟥/❌", "Śr. score", "Max"],
        stats_rows,
    ))

    lines.extend(["", "## Dzisiejsze runy na Pi", ""])

    jf_log = _read_cache_log(cache_dir, f"job_finder_{d}.log")
    rag_log = _read_cache_log(cache_dir, f"rag_fullrun_{d}.log")
    mr_log = _read_cache_log(cache_dir, f"my_resume_{d}.log")

    lines.append("### job_finder")
    lines.append("")
    for ln in jf_log[-5:]:
        lines.append(f"- `{ln}`")
    lines.append("")
    lines.append("### my_resume_rag")
    lines.append("")
    for ln in rag_log:
        if "KPI source=" in ln or "Completed:" in ln or "fullrun" in ln:
            lines.append(f"- `{ln.split(' - ', 3)[-1] if ' - ' in ln else ln}`")

    metrics_path = cache_dir / "run_metrics.json"
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        lines.append("")
        lines.append(f"- **run_metrics:** jobs_total={metrics.get('jobs_total')}, "
                     f"llm_calls={metrics.get('llm_calls')}, "
                     f"tiers={metrics.get('tier_counts')}")

    lines.extend(["", "### My resume", ""])
    if mr_log:
        for ln in mr_log:
            lines.append(f"- `{ln}`")
    else:
        lines.append("- Brak podsumowania w cache logu (log niekompletny w tail).")

    lines.extend([
        "",
        f"### WorkSphere",
        "",
        f"- **{n}** ofert z `first_seen == {d}`",
        "",
        f"## Nakładanie URL (WorkSphere dziś vs Pi{' delta' if result.delta_mode else ' kumulatywnie'})",
        "",
    ])

    overlap_rows = []
    for app in ("job_finder", "my_resume", "my_resume_rag"):
        ov = result.overlap_by_app[app]
        overlap_rows.append([app, str(len(ov)), f"{100 * len(ov) / n:.1f}%" if n else "0%"])
    overlap_rows.append(["**dowolna z 3**", f"**{len(result.any_remote)}**", f"**{100 * len(result.any_remote) / n:.1f}%**" if n else "0%"])
    overlap_rows.append(["**tylko w WorkSphere**", f"**{len(result.only_worksphere)}**", f"**{100 * len(result.only_worksphere) / n:.1f}%**" if n else "0%"])
    lines.append(_md_table(["Aplikacja", "Wspólne URL", "% z WorkSphere dziś"], overlap_rows))

    lines.extend(["", "## Macierz WorkSphere fit × remote verdict (overlap)", ""])
    for app in ("job_finder", "my_resume", "my_resume_rag"):
        cross = result.cross_tabs[app]
        if not cross:
            lines.append(f"### {app}")
            lines.append("")
            lines.append("Brak wspólnych URL.")
            lines.append("")
            continue
        lines.append(f"### {app}")
        lines.append("")
        cross_rows = [[fit, ver, str(cnt)] for (fit, ver), cnt in cross.most_common()]
        lines.append(_md_table(["WorkSphere fit", "Remote verdict", "Liczba"], cross_rows))
        lines.append("")

    lines.extend(["## Wspólne oferty (pełny scoring)", ""])
    common_rows: list[list[str]] = []
    for url in sorted(result.any_remote, key=lambda u: ws[u].title):
        b = ws[url]
        row = [
            _escape_md(b.title, 45),
            _escape_md(b.company, 25),
            b.portal,
            b.fit,
        ]
        for app in ("job_finder", "my_resume", "my_resume_rag"):
            if url in result.remote[app]:
                r = result.remote[app][url]
                row.append(f"{r.verdict} {r.score if r.score is not None else '—'}")
            else:
                row.append("—")
        row.append(f"[link]({b.url})")
        common_rows.append(row)

    lines.append(_md_table(
        ["Tytuł", "Firma", "Portal", "WorkSphere", "JF", "MR", "RAG", "URL"],
        common_rows,
    ))

    lines.extend(["", "## Rozbieżności scoringu", ""])

    high_red: list[str] = []
    low_green: list[str] = []
    for url in result.any_remote:
        b = ws[url]
        for app in ("job_finder", "my_resume", "my_resume_rag"):
            if url not in result.remote[app]:
                continue
            r = result.remote[app][url]
            if b.fit == "high" and r.verdict in ("🟥", "❌"):
                high_red.append(
                    f"- **[{app}]** WorkSphere=`high`, remote=`{r.verdict}` score={r.score} — "
                    f"{_escape_md(b.title, 60)} ({_escape_md(b.company, 30)})"
                )
            if b.fit == "low" and r.verdict == "✅":
                low_green.append(
                    f"- **[{app}]** WorkSphere=`low`, remote=`✅` score={r.score} — "
                    f"{_escape_md(b.title, 60)}"
                )

    lines.append("### WorkSphere `high` + remote `🟥`/`❌`")
    lines.append("")
    if high_red:
        lines.extend(high_red)
    else:
        lines.append("Brak na overlapie.")
    lines.append("")
    lines.append("### WorkSphere `low` + remote `✅`")
    lines.append("")
    if low_green:
        lines.extend(low_green)
    else:
        lines.append("Brak na overlapie.")

    lines.extend(["", "## Tylko w WorkSphere (brak w żadnej aplikacji Pi)", ""])
    only_portal = Counter(ws[u].portal for u in result.only_worksphere)
    only_fit = Counter(ws[u].fit for u in result.only_worksphere)
    lines.append(f"- **Liczba:** {len(result.only_worksphere)}")
    lines.append(f"- **Portale:** {dict(only_portal)}")
    lines.append(f"- **Fit:** {dict(only_fit)}")
    lines.append("")
    lines.append("### Przykłady `high` / `medium` (tylko WorkSphere)")
    lines.append("")
    examples = []
    for url in result.only_worksphere:
        b = ws[url]
        if b.fit in ("high", "medium"):
            examples.append((0 if b.fit == "high" else 1, b.fit, b))
    examples.sort(key=lambda x: (x[0], x[2].title))
    ex_rows = [[e[1], _escape_md(e[2].title, 50), _escape_md(e[2].company, 25), e[2].portal] for e in examples[:15]]
    if ex_rows:
        lines.append(_md_table(["Fit", "Tytuł", "Firma", "Portal"], ex_rows))
    else:
        lines.append("Brak.")

    lines.extend(["", "## Oferty ✅ na Pi bez odpowiednika w WorkSphere dziś", ""])
    worksphere_urls = set(ws)
    pi_green_missing = []
    for app in ("job_finder", "my_resume", "my_resume_rag"):
        for url, job in result.remote[app].items():
            if job.verdict != "✅":
                continue
            if url in worksphere_urls:
                continue
            pi_green_missing.append((app, job))
    pi_green_missing.sort(key=lambda x: (-(x[1].score or 0), x[1].title))
    green_rows = [
        [app, str(job.score or "—"), _escape_md(job.title, 45), _escape_md(job.company, 25)]
        for app, job in pi_green_missing[:20]
    ]
    lines.append(f"- **Łącznie ✅ poza WorkSphere dziś:** {len(pi_green_missing)}")
    lines.append("")
    if green_rows:
        lines.append(_md_table(["Aplikacja", "Score", "Tytuł", "Firma"], green_rows))
    else:
        lines.append("Brak.")

    lines.extend([
        "",
        "## Wnioski",
        "",
        f"1. **Niski overlap ({100 * len(result.any_remote) / n:.0f}%)** — systemy scrapują różne zbiory portali i filtrów; porównanie scoringu ma sens głównie na {len(result.any_remote)} wspólnych URL.",
        "2. **Różne skale oceny:** WorkSphere używa 3-poziomowego `quick_fit` (limit LLM ~5/run); Pi używa JOBFIT 0–100 z werdyktami emoji; RAG dodaje embedding pre-filter i salary gate.",
        f"3. **my_resume_rag** ocenia tylko podzbiór (dziś: 169 z 283 po filtrach); overlap z WorkSphere: {len(result.overlap_by_app['my_resume_rag'])} URL.",
        f"4. WorkSphere ma **{fit_dist.get('high', 0)} high** dziś vs kumulatywnie **{app_stats(result.remote['job_finder'])['good']}** / **{app_stats(result.remote['my_resume'])['good']}** / **{app_stats(result.remote['my_resume_rag'])['good']}** ✅ na Pi — różne progi i profile kandydata.",
        "",
        "## Ograniczenia",
        "",
        "- Porównanie URL nie łapie aliasów (np. różne warianty tej samej oferty LinkedIn).",
        "- Pi `report.csv` jest kumulatywny; WorkSphere filtruje tylko `first_seen == dziś`.",
        "- Heurystyka mapowania: high ≈ ✅/≥75, medium ≈ 🟨/50–74, low ≈ 🟥/<50 — w tabelach pokazano surowe wartości.",
        "",
    ])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat(), help="Compare date (YYYY-MM-DD)")
    parser.add_argument("--seen", type=Path, default=DEFAULT_SEEN)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--no-ssh", action="store_true", help="Skip SSH (requires local CSV cache)")
    parser.add_argument("--hours", type=int, default=48, help="Window for Pi 48h coverage stats")
    parser.add_argument("--delta", action="store_true", help="Compare Pi offers new since last cached report.csv")
    parser.add_argument(
        "--sync-pi-metadata",
        action="store_true",
        help="Update pi_score/pi_verdict on overlapping seen_jobs entries",
    )
    parser.add_argument("--import-pi-gaps", action="store_true", help="Import Pi-only offers into seen_jobs.json")
    parser.add_argument("--min-score", type=int, default=72, help="Min score for yellow verdict import")
    parser.add_argument("--import-all", action="store_true", help="Import all Pi-only jobs (noisy)")
    parser.add_argument("--dry-run", action="store_true", help="Show import count without writing")
    args = parser.parse_args()

    output = args.output or Path(str(DEFAULT_OUTPUT).format(date=args.date))
    result = build_comparison(args.date, args.seen, use_ssh=not args.no_ssh, delta=args.delta)
    report = render_report(result, args.cache_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")

    print(f"Report written: {output}")
    print(f"WorkSphere today: {len(result.worksphere_today)}")
    print(f"Overlap any remote: {len(result.any_remote)}")
    for app, ov in result.overlap_by_app.items():
        print(f"  {app}: {len(ov)}")

    worksphere_keys = load_worksphere_url_keys(args.seen)
    pi_jobs = collect_pi_jobs_48h(
        args.hours,
        use_ssh=not args.no_ssh,
        cache_dir=args.cache_dir,
    )
    missing = pi_jobs_missing_from_worksphere(pi_jobs, worksphere_keys)
    summary = coverage_summary(pi_jobs, worksphere_keys, hours=args.hours)
    summary_path = args.cache_dir / "coverage_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.update(
        {
            "compare_date": args.date,
            "worksphere_today": len(result.worksphere_today),
            "overlap_today": len(result.any_remote),
            "only_worksphere": len(result.only_worksphere),
            "delta_mode": result.delta_mode,
        }
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        f"Pi 48h coverage: {summary['overlap_with_worksphere']}/{summary['pi_scored_48h']} "
        f"({summary['overlap_pct']}%), pi_only={summary['pi_only']}"
    )

    if args.sync_pi_metadata:
        from app.services.pi_gap_sync import PiJob, portal_from_url

        merged: dict[str, PiJob] = {}
        for app in REMOTE_CSV:
            cache_file = args.cache_dir / f"{app}_report.csv"
            if not cache_file.exists():
                continue
            for url_key, remote in load_remote_csv(cache_file.read_text(encoding="utf-8")).items():
                job = PiJob(
                    url=remote.url,
                    title=remote.title,
                    company=remote.company,
                    score=remote.score,
                    verdict=remote.verdict,
                    apps=app,
                    portal=portal_from_url(remote.url),
                )
                existing = merged.get(url_key)
                if existing is None or (job.score or 0) > (existing.score or 0):
                    merged[url_key] = job
        overlap_keys = set(result.worksphere_today) & set(merged)
        n_sync = sync_pi_metadata(
            {k: merged[k] for k in overlap_keys},
            args.seen,
            dry_run=args.dry_run,
        )
        n_mark = mark_only_worksphere_deep_eval(
            set(result.worksphere_today),
            result.any_remote,
            args.seen,
            dry_run=args.dry_run,
        )
        label = "Would sync" if args.dry_run else "Synced"
        print(f"{label} pi metadata for {n_sync} offers; marked {n_mark} worksphere-only for deep eval")

    if args.import_pi_gaps:
        to_import = [
            j for j in missing
            if is_importable(j, min_score=args.min_score, import_all=args.import_all)
        ]
        n = import_pi_gaps(to_import, args.seen, dry_run=args.dry_run)
        label = "Would import" if args.dry_run else "Imported"
        print(f"{label} {n} Pi gap offers (filtered from {len(missing)} pi_only)")


if __name__ == "__main__":
    main()
