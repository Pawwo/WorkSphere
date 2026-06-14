#!/usr/bin/env python3
"""Debug LLM response degradation — writes NDJSON to .cursor/debug-664ce0.log"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / ".cursor" / "debug-664ce0.log"
SESSION = "664ce0"
RUN_ID = os.environ.get("DEBUG_RUN_ID", "baseline")
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.0.112:8006"


def log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    entry = {
        "sessionId": SESSION,
        "runId": RUN_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def completion(prompt: str, max_tokens: int, temperature: float = 0.1) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL.rstrip('/')}/v1/completions",
        data=json.dumps({"prompt": prompt, "max_tokens": max_tokens, "temperature": temperature}).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as r:
        body = json.load(r)
    elapsed = time.perf_counter() - t0
    text = body["choices"][0]["text"]
    return {"text": text, "elapsed_s": round(elapsed, 3), "len": len(text)}


def chat(messages: list, max_tokens: int, temperature: float = 0.0) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL.rstrip('/')}/v1/chat/completions",
        data=json.dumps({
            "model": "minitron-Bielik-7B-v3.0-Instruct-GGUF.Q4_K_M.gguf",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as r:
        body = json.load(r)
    elapsed = time.perf_counter() - t0
    text = body["choices"][0]["message"]["content"]
    return {"text": text, "elapsed_s": round(elapsed, 3), "len": len(text)}


def analyze_text(text: str) -> dict:
    esc = text.count("\x1b")
    hashes = text.count("#")
    # first ESC or hash run position
    first_esc = text.find("\x1b")
    first_hash_run = re.search(r"#{4,}", text)
    return {
        "esc_count": esc,
        "esc_ratio": round(esc / max(len(text), 1), 4),
        "hash_count": hashes,
        "first_esc_pos": first_esc if first_esc >= 0 else None,
        "first_hash_run_pos": first_hash_run.start() if first_hash_run else None,
        "sample": text[:120],
    }


def ssh_backend_info() -> dict:
    try:
        out = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "root@192.168.0.112",
             "ps aux | grep '[l]lama-server.*8006'; "
             "nm -D /usr/local/lib/libggml-vulkan.so.0.14.0 2>/dev/null | grep -c ' U matmul' || echo 0; "
             "ls -la /usr/local/lib/libggml-vulkan.so.0.14.0"],
            capture_output=True, text=True, timeout=15,
        )
        line = out.stdout.strip().split("\n")[0] if out.stdout else ""
        ngl = 0
        if "-ngl" in line:
            m = re.search(r"-ngl\s+(\d+)", line)
            if m:
                ngl = int(m.group(1))
        return {"process_line": line[:200], "ngl": ngl, "ssh_raw": out.stdout[:500]}
    except Exception as exc:
        return {"error": str(exc)}


def main() -> None:
    # #region agent log
    backend = ssh_backend_info()
    log("A", "debug_llm_degradation.py:backend", "server backend info", backend)
    # #endregion

    # Hypothesis A: degradation scales with max_tokens (GPU matmul corruption after N tokens)
    prompt_json = '{"overall_fit":'
    for mt in [8, 16, 32, 64, 128]:
        try:
            r = completion(prompt_json, mt)
            stats = analyze_text(r["text"])
            # #region agent log
            log("A", "debug_llm_degradation.py:completion_tokens", f"completions max_tokens={mt}", {**stats, "max_tokens": mt, **r})
            # #endregion
        except Exception as exc:
            log("A", "debug_llm_degradation.py:completion_tokens", f"FAIL max_tokens={mt}", {"error": str(exc)})

    # Hypothesis B: app chat path differs from raw completions
    prompt_plain = "The capital of Poland is"
    for endpoint, fn, kwargs in [
        ("completions", completion, {"prompt": prompt_plain, "max_tokens": 32}),
        ("chat", chat, {"messages": [{"role": "user", "content": prompt_plain}], "max_tokens": 32}),
    ]:
        try:
            r = fn(**kwargs) if endpoint == "completions" else fn(**kwargs)
            stats = analyze_text(r["text"])
            # #region agent log
            log("B", "debug_llm_degradation.py:endpoint", f"{endpoint} plain prompt", {**stats, "endpoint": endpoint, **r})
            # #endregion
        except Exception as exc:
            log("B", "debug_llm_degradation.py:endpoint", f"FAIL {endpoint}", {"error": str(exc)})

    # Hypothesis C: temperature 0 avoids degradation
    for temp in [0.0, 0.1, 0.7]:
        try:
            r = completion(prompt_json, 64, temperature=temp)
            stats = analyze_text(r["text"])
            # #region agent log
            log("C", "debug_llm_degradation.py:temperature", f"temp={temp}", {**stats, "temperature": temp})
            # #endregion
        except Exception as exc:
            log("C", "debug_llm_degradation.py:temperature", f"FAIL temp={temp}", {"error": str(exc)})

    # Hypothesis D: JSON-only short prompt OK, long system+user chat degrades (app pattern)
    try:
        sys.path.insert(0, str(ROOT))
        import asyncio
        from app.llm.client import BielikClient

        async def app_test():
            client = BielikClient()
            r = await client.chat_complete(
                [
                    {"role": "system", "content": "Jesteś asystentem. Zwracasz tylko JSON."},
                    {"role": "user", "content": 'Return JSON: {"overall_fit":"moderate","recommendation":"apply"}'},
                ],
                max_tokens=64,
                temperature=0.0,
            )
            return r

        raw = asyncio.run(app_test())
        stats = analyze_text(raw)
        # #region agent log
        log("D", "debug_llm_degradation.py:BielikClient", "app chat_complete", {**stats, "len": len(raw)})
        # #endregion
    except Exception as exc:
        log("D", "debug_llm_degradation.py:BielikClient", "FAIL app path", {"error": str(exc)})

    # Hypothesis E: degradation starts at fixed char offset regardless of prompt
    for prompt in ["Say: OK", "1+1=", '{"fit":']:
        try:
            r = completion(prompt, 48)
            stats = analyze_text(r["text"])
            # #region agent log
            log("E", "debug_llm_degradation.py:prompt_variety", f"prompt={prompt[:20]}", {**stats, "prompt": prompt})
            # #endregion
        except Exception as exc:
            log("E", "debug_llm_degradation.py:prompt_variety", "FAIL", {"error": str(exc), "prompt": prompt})

    print(f"Logs written to {LOG_PATH}")


if __name__ == "__main__":
    main()
