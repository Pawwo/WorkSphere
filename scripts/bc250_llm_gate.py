#!/usr/bin/env python3
"""BC-250 LLM quality/speed gates for Vulkan tuning experiments."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATES_LOG = ROOT / "data" / "llm_benchmark" / "gates.jsonl"
DEFAULT_URL = "http://192.168.0.112:8006"
DEFAULT_MODEL = "/root/models/bielik/minitron-Bielik-7B-v3.0-Instruct-GGUF.Q4_K_M.gguf"
SSH_HOST = "root@192.168.0.112"


def gate_a(base_url: str, max_tokens: int = 128) -> dict:
    prompt = '{"overall_fit":'
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/completions",
        data=json.dumps({"prompt": prompt, "max_tokens": max_tokens, "temperature": 0.1}).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as r:
        text = json.load(r)["choices"][0]["text"]
    esc = text.count("\x1b")
    ratio = esc / max(len(text), 1)
    return {
        "gate": "A",
        "pass": ratio < 0.01,
        "esc_count": esc,
        "esc_ratio": round(ratio, 4),
        "len": len(text),
        "sample": text[:100],
        "elapsed_s": round(time.perf_counter() - t0, 3),
    }


def gate_b_ssh(baseline_tg: float | None = None, min_tg: float = 50.0) -> dict:
    cmd = (
        f"LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/llama-bench "
        f"-m {DEFAULT_MODEL} -ngl 99 -p 128 -n 128 -r 3 2>/dev/null"
    )
    out = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=10", SSH_HOST, cmd],
        capture_output=True,
        text=True,
        timeout=300,
    )
    pp = tg = None
    for line in out.stdout.splitlines():
        if "pp128" in line:
            m = re.search(r"pp128\s*\|\s*([\d.]+)", line)
            if m:
                pp = float(m.group(1))
        if "tg128" in line:
            m = re.search(r"tg128\s*\|\s*([\d.]+)", line)
            if m:
                tg = float(m.group(1))
    build_m = re.search(r"build:\s*(\S+)", out.stdout)
    passed = False
    if tg is not None:
        if baseline_tg is not None:
            passed = tg >= baseline_tg
        else:
            passed = tg >= min_tg
    info = subprocess.run(
        ["ssh", SSH_HOST,
         "nm -D /usr/local/lib/libggml-vulkan.so.0.14.0 2>/dev/null | grep -c ' U matmul' || echo 0; "
         "ls -la /usr/local/lib/libggml-vulkan.so.0.14.0; "
         "/usr/local/bin/llama-server --version 2>/dev/null | head -1"],
        capture_output=True, text=True, timeout=30,
    )
    lines = info.stdout.strip().split("\n")
    undef = int(lines[0]) if lines and lines[0].isdigit() else -1
    return {
        "gate": "B",
        "pass": passed and tg is not None,
        "pp128": pp,
        "tg128": tg,
        "baseline_tg": baseline_tg,
        "min_tg": min_tg,
        "build": build_m.group(1) if build_m else None,
        "undef_matmul": undef,
        "bench_stdout_tail": out.stdout[-800:] if out.stdout else out.stderr[-400:],
    }


def append_log(exp_id: str, results: dict) -> None:
    GATES_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "exp_id": exp_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        **results,
    }
    with GATES_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="BC-250 LLM gates")
    p.add_argument("--exp", default="exp-000", help="Experiment id for logging")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--gate", choices=["A", "B", "AB", "ABC"], default="AB")
    p.add_argument("--baseline-tg", type=float, default=None)
    p.add_argument("--min-tg", type=float, default=50.0)
    p.add_argument("--skip-bench", action="store_true")
    args = p.parse_args()

    results: dict = {"gates": {}}
    exit_code = 0

    if args.gate in ("A", "AB", "ABC"):
        try:
            ga = gate_a(args.url)
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            ga = {"gate": "A", "pass": False, "error": str(exc)}
        results["gates"]["A"] = ga
        print(f"Gate A: {'PASS' if ga.get('pass') else 'FAIL'} esc_ratio={ga.get('esc_ratio')} sample={ga.get('sample', ga.get('error', ''))!r}")
        if not ga.get("pass"):
            exit_code = 1

    if args.gate in ("B", "AB", "ABC") and exit_code == 0 and not args.skip_bench:
        gb = gate_b_ssh(args.baseline_tg, args.min_tg)
        results["gates"]["B"] = gb
        print(f"Gate B: {'PASS' if gb.get('pass') else 'FAIL'} tg128={gb.get('tg128')} pp128={gb.get('pp128')}")
        if not gb.get("pass"):
            exit_code = 1

    if args.gate == "ABC" and exit_code == 0:
        print("Gate C: run manually: python scripts/benchmark_llm_models.py --model minitron-q4 --no-restore")
        results["gates"]["C"] = {"gate": "C", "pass": None, "note": "manual"}

    append_log(args.exp, results)
    print(f"Logged to {GATES_LOG}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
