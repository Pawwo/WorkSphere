#!/usr/bin/env python3
"""Benchmark local LLM models against all application prompt patterns.

Usage:
  python scripts/benchmark_llm_models.py --list-models
  python scripts/benchmark_llm_models.py --model minitron-q4
  python scripts/benchmark_llm_models.py --all
  python scripts/benchmark_llm_models.py --all --report docs/llm-model-comparison-2026-06-11.md
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.llm.client import BielikClient  # noqa: E402
from app.llm.structured import extract_json  # noqa: E402
from app.prompts.loader import render_prompt  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "llm_benchmark"
RESULTS_DIR = ROOT / "data" / "llm_benchmark"
SSH_HOST = os.environ.get("BENCHMARK_SSH_HOST", "")
BENCHMARK_PORT = 8006
BENCHMARK_HOST = os.environ.get("BENCHMARK_HOST", "127.0.0.1")

CHAT_SYSTEMD_UNITS = [
    "llama-server-bielik",
    "llama-server-bielik-cpu",
    "llama-server-bielik-11b",
    "llama-server-jina-embed",
    "llama-server-minitron",
    "llama-server-llama32",
    "llama-server-qwen",
    "llama-server-qwen25",
    "llama-server-qwen30-instruct",
    "llama-server-qwen36",
    "llama-server-qwen3coder",
]

GROUP_WEIGHTS = {"A": 0.50, "B": 0.30, "C": 0.20}


@dataclass
class ModelSpec:
    id: str
    label: str
    path: str
    ngl: int = 999
    context: int = 8192
    threads: int = 6
    batch_size: int = 128
    ubatch_size: int = 64
    extra_args: str = ""
    skip: str = ""


MODELS: list[ModelSpec] = [
    ModelSpec(
        "minitron-q4",
        "Bielik-Minitron-7B Q4_K_M",
        "/root/models/bielik/minitron-Bielik-7B-v3.0-Instruct-GGUF.Q4_K_M.gguf",
        ngl=999,
        batch_size=128,
        ubatch_size=64,
        extra_args="--repeat-penalty 1.1",
    ),
    ModelSpec("bielik-11b-q4", "Bielik-11B Q4_K_M", "/root/models/bielik/Bielik-11B-v3.0-Instruct.Q4_K_M.gguf", context=4096, threads=4, batch_size=512, ubatch_size=512),
    ModelSpec("bielik-11b-q6", "Bielik-11B Q6_K_L", "/root/models/bielik/speakleash_Bielik-11B-v3.0-Instruct-Q6_K_L.gguf", context=4096, threads=4, batch_size=512, ubatch_size=512),
    ModelSpec("minitron-q8", "Bielik-Minitron-7B Q8_0", "/root/models/minitron/minitron-Bielik-7B-v3.0-Instruct-GGUF.Q8_0.gguf"),
    ModelSpec("llama32-3b", "Llama-3.2-3B-Instruct Q4_K_M", "/root/models/llama32/Llama-3.2-3B-Instruct-Q4_K_M.gguf", threads=4, batch_size=512, ubatch_size=512),
    ModelSpec("qwen25-7b", "Qwen2.5-7B-Instruct Q4_K_M", "/root/models/qwen/Qwen2.5-7B-Instruct-Q4_K_M.gguf", threads=8, batch_size=512, ubatch_size=512),
    ModelSpec("qwen-9b", "Qwen3.5-9B Q4_K_M", "/root/models/qwen/qwen-9b-q4_km.gguf", context=16384, threads=4, batch_size=512, ubatch_size=512),
    ModelSpec("gemma4-4b", "Gemma 4B IT Q4_K_M", "/root/models/gemma4-e4b-it-q4_k_m.gguf", threads=4, batch_size=512, ubatch_size=512),
    ModelSpec("qwen36-27b", "Qwen3.6-27B Q3_K_M", "/root/models/qwen/Qwen3.6-27B-Q3_K_M.gguf", context=2560, batch_size=128, ubatch_size=64, extra_args="--jinja"),
    ModelSpec("qwen30-30b", "Qwen3-30B-A3B-Instruct Q4_K_M", "/root/models/qwen/Qwen3-30B-A3B-Instruct-2507-Q4_K_M.gguf", ngl=999, threads=8, batch_size=128, ubatch_size=64, extra_args="--jinja"),
    ModelSpec(
        "qwen35-35b",
        "Qwen3.5-35B-A3B Q4_K_M",
        "/root/models/qwen/Qwen3.5-35B-A3B-Q4_K_M.gguf",
        ngl=999,
        context=8192,
        threads=8,
        batch_size=128,
        ubatch_size=64,
        extra_args="--jinja",
    ),
    ModelSpec(
        "bielik-11b-q6-bench",
        "Bielik-11B Q6_K",
        "/root/models/bielik/Bielik-11B-v3.0-Instruct.Q6_K.gguf",
        context=4096,
        threads=4,
        batch_size=512,
        ubatch_size=512,
    ),
    ModelSpec("qwen3-coder-30b", "Qwen3-Coder-30B-A3B Q4_K_M", "/root/models/qwen/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf", ngl=30, threads=8, batch_size=128, ubatch_size=128),
]


@dataclass
class CaseResult:
    case_id: str
    group: str
    quality: float
    latency_ms: float
    error: str = ""
    response_preview: str = ""


@dataclass
class ModelResult:
    model_id: str
    model_label: str
    model_path: str
    base_url: str
    probe_ok: bool
    disqualified: bool
    disqualify_reason: str = ""
    cases: list[CaseResult] = field(default_factory=list)
    quality_score: float = 0.0
    speed_score: float = 0.0
    total_score: float = 0.0
    quick_fit_p95_ms: float = 0.0
    json_pass_rate: float = 0.0


def _ssh(cmd: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", SSH_HOST, cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _load_fixtures() -> dict[str, Any]:
    profile = (FIXTURES / "profile_excerpt.md").read_text(encoding="utf-8")
    framework = (FIXTURES / "evaluation_framework.md").read_text(encoding="utf-8")
    jobs = json.loads((FIXTURES / "jobs.json").read_text(encoding="utf-8"))
    cv_text = (FIXTURES / "cv_snippet.txt").read_text(encoding="utf-8")
    tailor = json.loads((FIXTURES / "tailor_context.json").read_text(encoding="utf-8"))
    return {
        "profile": profile,
        "framework": framework,
        "jobs": jobs,
        "cv_text": cv_text,
        "tailor": tailor,
    }


def stop_chat_servers() -> None:
    units = " ".join(CHAT_SYSTEMD_UNITS)
    script = f"""
set -e
systemctl stop {units} 2>/dev/null || true
systemctl disable --now llama-server-bielik-cpu 2>/dev/null || true
pkill -f 'llama-cli' 2>/dev/null || true
pkill -f 'llama-server.*--port 8006' 2>/dev/null || true
pkill -f 'llama-server.*8006' 2>/dev/null || true
for port in 8000 8002 8003 8004 8005 8006; do
  pid=$(ss -tlnp | grep ":$port " | sed -n 's/.*pid=\\([0-9]*\\).*/\\1/p' | head -1)
  if [ -n "$pid" ]; then
    proc=$(ps -p "$pid" -o comm= 2>/dev/null || true)
    if echo "$proc" | grep -q llama-server; then
      kill "$pid" 2>/dev/null || true
    fi
  fi
done
sleep 2
"""
    res = _ssh(script, timeout=120)
    if res.returncode != 0:
        print(f"WARN stop_chat_servers: {res.stderr.strip()}", file=sys.stderr)


def start_model(spec: ModelSpec, wait_seconds: int = 90) -> bool:
    stop_chat_servers()
    cmd = (
        f"LD_LIBRARY_PATH=/usr/local/lib nohup /usr/local/bin/llama-server "
        f"-m {spec.path} "
        f"-ngl {spec.ngl} "
        f"-c {spec.context} "
        f"-np 1 "
        f"--threads {spec.threads} "
        f"--batch-size {spec.batch_size} "
        f"--ubatch-size {spec.ubatch_size} "
        f"--host 0.0.0.0 "
        f"--port {BENCHMARK_PORT} "
        f"{spec.extra_args} "
        f"> /tmp/llama-benchmark.log 2>&1 &"
    )
    res = _ssh(cmd, timeout=30)
    if res.returncode != 0:
        print(f"FAIL start {spec.id}: {res.stderr}", file=sys.stderr)
        return False

    health_url = f"http://{BENCHMARK_HOST}:{BENCHMARK_PORT}/v1/models"
    for i in range(wait_seconds):
        time.sleep(1)
        check = subprocess.run(
            ["curl", "-sf", "--max-time", "3", health_url],
            capture_output=True,
            text=True,
        )
        if check.returncode == 0 and "data" in (check.stdout or ""):
            print(f"  Model {spec.id} ready after {i + 1}s")
            return True
    log = _ssh("tail -30 /tmp/llama-benchmark.log 2>/dev/null || true", timeout=15)
    print(f"FAIL healthcheck {spec.id} after {wait_seconds}s\n{log.stdout}", file=sys.stderr)
    return False


def restore_default_server() -> None:
    stop_chat_servers()
    _ssh(
        "systemctl disable --now llama-server-bielik-cpu 2>/dev/null || true; "
        "systemctl enable --now llama-server-bielik",
        timeout=60,
    )


def _json_quality(parsed: Any, required: list[str]) -> float:
    if not isinstance(parsed, dict):
        return 0.0
    missing = [k for k in required if k not in parsed or parsed[k] in (None, "", [])]
    if not missing:
        return 100.0
    if len(missing) < len(required):
        return 50.0
    return 0.0


def build_cases(fixtures: dict[str, Any]) -> list[dict[str, Any]]:
    profile = fixtures["profile"]
    framework = fixtures["framework"]
    jobs = fixtures["jobs"]
    cv_text = fixtures["cv_text"]
    tailor = fixtures["tailor"]
    tailor_job = jobs["tailor_job"]

    salary_note = (
        "Wynagrodzenie (B2B/mies. szac.): 30000 PLN, próg: 25000 PLN, "
        "źródło: benchmark, OK."
    )

    return [
        {
            "id": "quick_fit_high",
            "group": "A",
            "weight": 0.125,
            "kind": "quick_fit",
            "expected": "high",
            "job": jobs["quick_fit_high"],
        },
        {
            "id": "quick_fit_low",
            "group": "A",
            "weight": 0.125,
            "kind": "quick_fit",
            "expected": "low",
            "job": jobs["quick_fit_low"],
        },
        {
            "id": "quick_fit_medium",
            "group": "A",
            "weight": 0.125,
            "kind": "quick_fit",
            "expected": "medium",
            "job": jobs["quick_fit_medium"],
        },
        {
            "id": "quick_fit_security",
            "group": "A",
            "weight": 0.125,
            "kind": "quick_fit",
            "expected": "low",
            "job": jobs["quick_fit_security"],
        },
        {
            "id": "evaluate_fit",
            "group": "A",
            "kind": "chat",
            "system": "Zwracasz tylko JSON.",
            "prompt": render_prompt(
                "evaluate_fit.jinja2",
                profile_excerpt=profile[:2000],
                evaluation_framework=framework[:1500],
                job_posting=jobs["evaluate_job"]["raw_text"][:2000],
                salary_assessment=salary_note,
            ),
            "max_tokens": 512,
            "temperature": 0.1,
            "validate": lambda p: _json_quality(p, ["skills_match", "overall_fit", "recommendation"]),
        },
        {
            "id": "job_posting_targets",
            "group": "A",
            "kind": "chat",
            "system": "JSON only.",
            "prompt": render_prompt(
                "job_posting_targets.jinja2",
                role=tailor_job["role"],
                company=tailor_job["company"],
                job_posting=tailor_job["raw_text"][:2000],
            ),
            "max_tokens": 256,
            "temperature": 0.0,
            "validate": lambda p: _json_quality(p, ["must_have_keywords"]),
        },
        {
            "id": "draft_cv_header",
            "group": "A",
            "kind": "chat",
            "system": "JSON only.",
            "prompt": render_prompt(
                "draft_cv_header.jinja2",
                role=tailor_job["role"],
                company=tailor_job["company"],
                job_targets_json=tailor["targets_json"],
                profile=profile[:1500],
                competencies_baseline=tailor["competencies_baseline"],
                master_summary=tailor["master_summary"],
                cv_language_name="English",
            ),
            "max_tokens": 384,
            "temperature": 0.1,
            "validate": lambda p: _json_quality(p, ["profile_statement", "competencies"]),
        },
        {
            "id": "draft_cv_experience",
            "group": "A",
            "kind": "chat",
            "system": "JSON only. Tailor experience bullets.",
            "prompt": render_prompt(
                "draft_cv_experience.jinja2",
                role=tailor_job["role"],
                company=tailor_job["company"],
                job_targets_json=tailor["targets_json"],
                experience_source=tailor["experience_source"],
                first_batch=True,
                cv_language_name="English",
            ),
            "max_tokens": 512,
            "temperature": 0.15,
            "validate": lambda p: _json_quality(p, ["experience_entries"]),
        },
        {
            "id": "draft_cover",
            "group": "B",
            "kind": "chat",
            "system": "JSON only.",
            "prompt": render_prompt(
                "draft_cover.jinja2",
                language="en",
                job_targets_json=tailor["targets_json"],
                profile=profile[:1200],
                behavioral=tailor["behavioral"],
                role=tailor_job["role"],
                company=tailor_job["company"],
                job_posting=tailor_job["raw_text"][:1200],
            ),
            "max_tokens": 384,
            "temperature": 0.25,
            "validate": lambda p: _json_quality(p, ["opening", "body", "closing"]),
        },
        {
            "id": "reviewer",
            "group": "B",
            "kind": "chat",
            "system": "JSON only",
            "prompt": render_prompt(
                "reviewer.jinja2",
                profile_excerpt=profile[:1200],
                job_posting=tailor_job["raw_text"][:1200],
                cv_draft=tailor["cv_draft_snippet"],
                cover_draft=tailor["cover_draft_snippet"],
                company_snippets=tailor["company_snippets"],
            ),
            "max_tokens": 384,
            "temperature": 0.2,
            "validate": lambda p: _json_quality(p, ["overall_verdict", "structured_edits"]),
        },
        {
            "id": "cv_extract",
            "group": "B",
            "kind": "chat",
            "system": "Jesteś parserem CV. Zwracasz tylko JSON.",
            "prompt": render_prompt("cv_extract.jinja2", cv_text=cv_text[:1400]),
            "max_tokens": 1536,
            "temperature": 0.0,
            "validate": lambda p: _json_quality(p, ["identity"]),
        },
        {
            "id": "cv_career_infer",
            "group": "B",
            "kind": "chat",
            "system": "Jesteś parserem CV. Zwracasz tylko JSON.",
            "prompt": render_prompt(
                "cv_career_infer.jinja2",
                full_name="Jan Kowalski",
                location="Szczecin",
                roles=["Chief Operating Officer", "Founder", "Manager Business Development"],
                programming="Python",
                domain="Odoo ERP, Operations, AI Transformation",
                tools="Odoo, Docker, Jira",
                cv_snippet=cv_text[:1200],
            ),
            "max_tokens": 1024,
            "temperature": 0.0,
            "validate": lambda p: _json_quality(p, ["target_roles", "role_titles"]),
        },
        {
            "id": "job_highlights",
            "group": "B",
            "kind": "chat",
            "system": "JSON only",
            "prompt": render_prompt(
                "job_highlights.jinja2",
                profile_excerpt=profile[:1500],
                job=jobs["quick_fit_high"],
            ),
            "max_tokens": 512,
            "temperature": 0.2,
            "validate": lambda p: _json_quality(p, ["highlights"]),
        },
        {
            "id": "job_parse",
            "group": "B",
            "kind": "chat",
            "system": "JSON only",
            "prompt": render_prompt("job_parse.jinja2", text=jobs["parse_job_text"]),
            "max_tokens": 256,
            "temperature": 0.0,
            "validate": lambda p: _json_quality(p, ["company", "role", "location"]),
        },
        {
            "id": "behavioral_synthesis",
            "group": "C",
            "kind": "chat",
            "system": "Zwracasz tylko JSON.",
            "prompt": render_prompt(
                "behavioral_synthesis.jinja2",
                thrive_in="Scaling operations teams and ERP delivery",
                drains_energy="Micromanagement without autonomy",
                team_style="Collaborative, data-informed",
                decision_style="Analytical with fast iteration",
                communication_style="Direct and structured",
                notes="",
            ),
            "max_tokens": 1024,
            "temperature": 0.2,
            "validate": lambda p: _json_quality(p, ["summary", "strengths"]),
        },
        {
            "id": "interview_prep",
            "group": "C",
            "kind": "chat",
            "system": "Write markdown only.",
            "prompt": render_prompt(
                "interview_prep.jinja2",
                interview_framework=framework[:400],
                profile=profile[:400],
                job_posting=tailor_job["raw_text"][:600],
                role=tailor_job["role"],
                company=tailor_job["company"],
                language="English",
            ),
            "max_tokens": 512,
            "temperature": 0.3,
            "validate": lambda text: (
                100.0
                if isinstance(text, str) and len(text) > 200 and "##" in text
                else (50.0 if isinstance(text, str) and len(text) > 100 else 0.0)
            ),
            "raw_text": True,
        },
        {
            "id": "expand_extract",
            "group": "C",
            "kind": "chat",
            "system": "JSON only",
            "prompt": render_prompt(
                "expand_extract.jinja2",
                existing_profile=profile[:2000],
                sources_text=tailor["expand_sources"][:3000],
            ),
            "max_tokens": 3000,
            "temperature": 0.1,
            "validate": lambda p: _json_quality(p, ["competencies"]),
        },
        {
            "id": "upskill_synthesis",
            "group": "C",
            "kind": "chat",
            "system": "JSON only",
            "prompt": render_prompt(
                "upskill_synthesis.jinja2",
                profile=profile[:2000],
                jobs_context=tailor["jobs_context"][:3000],
                mode="gaps",
            ),
            "max_tokens": 3000,
            "temperature": 0.2,
            "validate": lambda p: _json_quality(p, ["gaps", "learning_plan"]),
        },
    ]


async def run_case(client: BielikClient, case: dict[str, Any], profile: str) -> CaseResult:
    t0 = time.perf_counter()
    try:
        if case.get("kind") == "quick_fit":
            raw = await client.quick_fit(profile[:2000], case["job"])
            quality = 100.0 if raw == case["expected"] else 0.0
            preview = raw
        else:
            raw = await client.chat_complete(
                [
                    {"role": "system", "content": case["system"]},
                    {"role": "user", "content": case["prompt"]},
                ],
                max_tokens=case["max_tokens"],
                temperature=case["temperature"],
            )
            if case.get("raw_text"):
                quality = case["validate"](raw)
                preview = raw[:200]
            else:
                parsed = extract_json(raw)
                quality = case["validate"](parsed)
                preview = (raw or "")[:200]
        latency = (time.perf_counter() - t0) * 1000
        return CaseResult(
            case_id=case["id"],
            group=case["group"],
            quality=quality,
            latency_ms=latency,
            response_preview=preview.replace("\n", " ")[:200],
        )
    except Exception as exc:
        latency = (time.perf_counter() - t0) * 1000
        return CaseResult(
            case_id=case["id"],
            group=case["group"],
            quality=0.0,
            latency_ms=latency,
            error=str(exc)[:300],
        )


async def benchmark_model(spec: ModelSpec, cases: list[dict[str, Any]], fixtures: dict[str, Any]) -> ModelResult:
    base_url = f"http://{BENCHMARK_HOST}:{BENCHMARK_PORT}/v1"
    llm_timeout = 420 if spec.ngl == 0 else 180
    settings = get_settings().model_copy(
        update={
            "llm_base_url": base_url,
            "llm_model": Path(spec.path).name,
            "llm_model_file": Path(spec.path).name,
            "llm_concurrency": 1,
            "llm_context_size": spec.context,
            "llm_timeout_seconds": llm_timeout,
        }
    )
    client = BielikClient(settings)
    client._resolved_model = None

    result = ModelResult(
        model_id=spec.id,
        model_label=spec.label,
        model_path=spec.path,
        base_url=base_url,
        probe_ok=False,
        disqualified=False,
    )

    probe_ok = await client.probe_chat()
    result.probe_ok = probe_ok
    if not probe_ok:
        result.disqualified = True
        result.disqualify_reason = "probe_chat failed"
        return result

    profile = fixtures["profile"]
    for case in cases:
        print(f"    case {case['id']}...", flush=True)
        cr = await run_case(client, case, profile)
        result.cases.append(cr)
        status = "OK" if cr.quality >= 50 else "FAIL"
        print(f"      {status} quality={cr.quality:.0f} latency={cr.latency_ms:.0f}ms", flush=True)

    return result


def score_model(result: ModelResult, all_results: list[ModelResult]) -> ModelResult:
    if result.disqualified:
        return result

    group_quality: dict[str, list[float]] = {"A": [], "B": [], "C": []}
    group_latency: dict[str, list[float]] = {"A": [], "B": [], "C": []}
    json_cases = 0
    json_pass = 0
    qf_latencies: list[float] = []

    for c in result.cases:
        group_quality[c.group].append(c.quality)
        group_latency[c.group].append(c.latency_ms)
        if c.case_id.startswith("quick_fit"):
            qf_latencies.append(c.latency_ms)
        if c.case_id not in ("interview_prep",) and not c.case_id.startswith("quick_fit"):
            json_cases += 1
            if c.quality >= 50:
                json_pass += 1

    quality_parts = []
    for g, w in GROUP_WEIGHTS.items():
        vals = group_quality[g]
        quality_parts.append((statistics.mean(vals) if vals else 0.0) * w)
    result.quality_score = sum(quality_parts)

    all_latencies = [c.latency_ms for c in result.cases if c.latency_ms > 0]
    model_avg = statistics.mean(all_latencies) if all_latencies else 999999.0
    fastest = min(
        statistics.mean([c.latency_ms for c in r.cases if c.latency_ms > 0] or [999999.0])
        for r in all_results
        if not r.disqualified and r.cases
    )
    result.speed_score = min(100.0, (fastest / model_avg) * 100.0) if model_avg > 0 else 0.0
    result.total_score = 0.6 * result.quality_score + 0.4 * result.speed_score
    result.quick_fit_p95_ms = statistics.quantiles(qf_latencies, n=20)[-1] if len(qf_latencies) >= 2 else (qf_latencies[0] if qf_latencies else 0.0)
    result.json_pass_rate = (json_pass / json_cases * 100.0) if json_cases else 0.0

    group_a_fails = sum(1 for c in result.cases if c.group == "A" and c.quality == 0)
    qf_avg = statistics.mean(qf_latencies) if qf_latencies else 0.0
    if group_a_fails > 2:
        result.disqualified = True
        result.disqualify_reason = f">{group_a_fails} group-A failures"
    elif qf_avg > 15000:
        result.disqualified = True
        result.disqualify_reason = f"quick_fit avg {qf_avg:.0f}ms > 15s"

    return result


def rescore_from_json(model_ids: list[str], report: str = "") -> list[ModelResult]:
    results: list[ModelResult] = []
    for mid in model_ids:
        path = RESULTS_DIR / f"{mid}.json"
        if not path.exists():
            print(f"MISSING {path}", file=sys.stderr)
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        cases = [CaseResult(**c) for c in data["cases"]]
        results.append(
            ModelResult(
                model_id=data["model_id"],
                model_label=data["model_label"],
                model_path=data["model_path"],
                base_url=data["base_url"],
                probe_ok=data["probe_ok"],
                disqualified=data.get("disqualified", False),
                disqualify_reason=data.get("disqualify_reason", ""),
                cases=cases,
            )
        )
    for r in results:
        score_model(r, results)
    if report:
        write_report(Path(report), results, discover_infra())
    return results


def write_report(path: Path, results: list[ModelResult], infra: str) -> None:
    ranked = sorted(
        [r for r in results if not r.disqualified],
        key=lambda r: r.total_score,
        reverse=True,
    )
    disqualified = [r for r in results if r.disqualified]

    lines = [
        f"# Porównanie modeli LLM ({date.today().isoformat()})",
        "",
        "Wygenerowano przez `scripts/benchmark_llm_models.py`.",
        "",
        "## Infrastruktura",
        "",
        infra,
        "",
        "## Ranking (balanced: 60% jakość + 40% prędkość)",
        "",
        "| Model | Jakość | Prędkość | Wynik | quick_fit p95 | JSON pass |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in ranked:
        lines.append(
            f"| {r.model_label} | {r.quality_score:.1f} | {r.speed_score:.1f} | "
            f"**{r.total_score:.1f}** | {r.quick_fit_p95_ms:.0f}ms | {r.json_pass_rate:.0f}% |"
        )

    if disqualified:
        lines.extend(["", "## Dyskwalifikacje", ""])
        for r in disqualified:
            lines.append(f"- **{r.model_label}**: {r.disqualify_reason}")

    if ranked:
        winner = ranked[0]
        lines.extend(
            [
                "",
                "## Rekomendacja",
                "",
                f"**{winner.model_label}** (`{Path(winner.model_path).name}`) — "
                f"wynik {winner.total_score:.1f}/100, jakość {winner.quality_score:.1f}, "
                f"quick_fit p95 {winner.quick_fit_p95_ms:.0f}ms.",
                "",
                "## Per-case — szczegóły",
                "",
            ]
        )
        for r in ranked:
            lines.append(f"### {r.model_label}")
            lines.append("")
            lines.append("| Case | Jakość | Latencja |")
            lines.append("| --- | --- | --- |")
            for c in r.cases:
                lines.append(f"| {c.case_id} | {c.quality:.0f} | {c.latency_ms:.0f}ms |")
            lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {path}")


def discover_infra() -> str:
    res = _ssh(
        'echo "Host: $(hostname)"; '
        'echo "Models:"; find /root/models -name "*.gguf" -type f | wc -l; '
        'echo "GPU:"; (lspci | grep -i vga || true); '
        'echo "Active chat:"; ss -tlnp | grep -E "800[0-7]" || true',
        timeout=30,
    )
    return res.stdout.strip() or res.stderr.strip()


async def main_async(args: argparse.Namespace) -> int:
    fixtures = _load_fixtures()
    cases = build_cases(fixtures)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.list_models:
        for m in MODELS:
            flag = f" SKIP: {m.skip}" if m.skip else ""
            print(f"{m.id:20} {m.label}{flag}")
        return 0

    specs = [m for m in MODELS if m.id in args.model] if args.model else MODELS
    specs = [m for m in specs if not m.skip]

    infra = discover_infra()
    print(infra)
    results: list[ModelResult] = []

    try:
        for spec in specs:
            print(f"\n=== {spec.label} ({spec.id}) ===")
            if not start_model(spec, wait_seconds=args.wait):
                results.append(
                    ModelResult(
                        model_id=spec.id,
                        model_label=spec.label,
                        model_path=spec.path,
                        base_url=f"http://{BENCHMARK_HOST}:{BENCHMARK_PORT}/v1",
                        probe_ok=False,
                        disqualified=True,
                        disqualify_reason="failed to start or healthcheck",
                    )
                )
                continue

            mr = await benchmark_model(spec, cases, fixtures)
            out = RESULTS_DIR / f"{spec.id}.json"
            out.write_text(
                json.dumps(
                    {
                        **asdict(mr),
                        "cases": [asdict(c) for c in mr.cases],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            results.append(mr)
    finally:
        if not args.no_restore:
            print("\nRestoring default llama-server-bielik service...")
            restore_default_server()

    for r in results:
        score_model(r, results)

    ranked = sorted(results, key=lambda r: (r.disqualified, -r.total_score))
    print("\n=== RANKING ===")
    for r in ranked:
        tag = "DQ" if r.disqualified else "OK"
        print(
            f"[{tag}] {r.model_label:30} total={r.total_score:5.1f} "
            f"quality={r.quality_score:5.1f} speed={r.speed_score:5.1f} "
            f"qf_p95={r.quick_fit_p95_ms:6.0f}ms"
        )

    if args.report:
        write_report(Path(args.report), results, infra)

    _print_scrape_time_estimate()

    return 0


def _print_scrape_time_estimate() -> None:
    """Rough LLM-only scrape duration estimate from token budget."""
    try:
        from app.config import get_settings

        s = get_settings()
        limit = int(s.scrape_llm_fit_limit or 40)
        tg = 42.0
        sec_per_quick_fit = (16 + 80) / tg  # ~16 out tok + ~80 prompt prefill equiv
        est = limit * sec_per_quick_fit
        print(
            f"\n=== Scrape LLM estimate (llm_fit_limit={limit}, ~{tg:.0f} tok/s) ===\n"
            f"  quick_fit serial: ~{est:.0f}s per batch (+ highlights/language triage extra)\n"
            f"  persistent fit cache: data/fit_cache.json"
        )
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark LLM models for WorkSphere")
    parser.add_argument("--list-models", action="store_true")
    parser.add_argument("--model", action="append", help="Model id (repeatable); default all")
    parser.add_argument("--all", action="store_true", help="Benchmark all models")
    parser.add_argument("--wait", type=int, default=90, help="Seconds to wait for model ready")
    parser.add_argument("--report", type=str, default="", help="Output markdown report path")
    parser.add_argument("--no-restore", action="store_true", help="Do not restore default service after run")
    parser.add_argument(
        "--rescore",
        nargs="+",
        metavar="MODEL_ID",
        help="Re-score from data/llm_benchmark/<id>.json (no LLM run); use with --report",
    )
    args = parser.parse_args()
    if args.rescore:
        results = rescore_from_json(args.rescore, report=args.report)
        print("\n=== RANKING ===")
        for r in sorted(results, key=lambda x: (x.disqualified, -x.total_score)):
            tag = "DQ" if r.disqualified else "OK"
            print(
                f"[{tag}] {r.model_label:30} total={r.total_score:5.1f} "
                f"quality={r.quality_score:5.1f} speed={r.speed_score:5.1f} "
                f"qf_p95={r.quick_fit_p95_ms:6.0f}ms"
            )
        raise SystemExit(0)
    if args.all and not args.report:
        args.report = str(ROOT / f"docs/llm-model-comparison-{date.today().isoformat()}.md")
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
