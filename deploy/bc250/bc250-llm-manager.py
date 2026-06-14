#!/usr/bin/env python3
"""LAN-only LLM power manager for BC-250 (wake / sleep / status)."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HOST = "0.0.0.0"
PORT = 8099
ACTIVITY_FILE = Path("/var/run/bc250-llm.last_activity")
LLM_URL = "http://127.0.0.1:8006/v1/models"
# Vulkan unit (llama-server-bielik) corrupts logits after ~20 decode tokens on RADV GFX1013.
LLM_UNIT = "llama-server-bielik"
WAKE_TIMEOUT_S = 90
GPU_PERF = "/usr/local/bin/bc250-gpu-performance.sh"
GPU_IDLE = "/usr/local/bin/bc250-gpu-idle.sh"


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd, check=False).returncode


def _touch_activity() -> None:
    ACTIVITY_FILE.write_text(str(int(time.time())))


def _last_activity() -> int | None:
    if not ACTIVITY_FILE.exists():
        return None
    try:
        return int(ACTIVITY_FILE.read_text().strip())
    except ValueError:
        return None


def _llm_ready() -> bool:
    try:
        with urllib.request.urlopen(LLM_URL, timeout=3) as resp:
            data = json.loads(resp.read())
        return bool(data.get("models") or data.get("data"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False


def _service_active(unit: str) -> bool:
    out = subprocess.run(
        ["systemctl", "is-active", unit],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip() == "active"


def _ppt_w() -> str | None:
    try:
        out = subprocess.run(
            ["sensors", "amdgpu-pci-0100"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in out.stdout.splitlines():
            if line.strip().startswith("PPT:"):
                return line.split(":")[1].strip().split()[0]
    except OSError:
        pass
    return None


def wake() -> dict:
    if LLM_UNIT == "llama-server-bielik":
        _run([GPU_PERF])
    if not _service_active(LLM_UNIT):
        _run(["systemctl", "start", LLM_UNIT])
    deadline = time.time() + WAKE_TIMEOUT_S
    while time.time() < deadline:
        if _llm_ready():
            _touch_activity()
            return {"ok": True, "llm": "ready"}
        time.sleep(1.0)
    return {"ok": False, "llm": "starting", "error": "timeout waiting for :8006"}


def sleep() -> dict:
    _run(["systemctl", "stop", LLM_UNIT])
    _run(["systemctl", "stop", "llama-server-bielik"])  # legacy Vulkan unit if left running
    _run(["systemctl", "stop", "llama-server-jina-embed"])
    _run([GPU_IDLE])
    return {"ok": True, "llm": "stopped"}


def status() -> dict:
    bielik = _service_active(LLM_UNIT)
    jina = _service_active("llama-server-jina-embed")
    ready = bielik and _llm_ready()
    llm_state = "ready" if ready else ("starting" if bielik else "stopped")
    return {
        "ok": True,
        "llm": llm_state,
        "llm_unit": LLM_UNIT,
        "llama_server_bielik": bielik,
        "llama_server_jina": jina,
        "last_activity": _last_activity(),
        "ppt_w": _ppt_w(),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") in ("", "/status"):
            self._json(200, status())
            return
        self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        path = self.path.rstrip("/")
        if path == "/wake":
            result = wake()
            self._json(200 if result.get("ok") else 503, result)
            return
        if path == "/sleep":
            self._json(200, sleep())
            return
        if path == "/activity":
            _touch_activity()
            self._json(200, {"ok": True})
            return
        self._json(404, {"ok": False, "error": "not found"})


def main() -> None:
    HTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
