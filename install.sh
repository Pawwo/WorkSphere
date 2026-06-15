#!/usr/bin/env bash
# WorkSphere — installer for Linux (x86_64 and aarch64/arm64).
# Installs Python deps, Bun scrapers, Playwright (HTML→PDF), and optional SearXNG.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ARCH_LABEL="x86_64" ;;
  aarch64|arm64) ARCH_LABEL="arm64" ;;
  *)
    echo "Unsupported architecture: $ARCH (need x86_64 or aarch64/arm64)" >&2
    exit 1
    ;;
esac

echo "=== WorkSphere install ($ARCH_LABEL) ==="

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || return 1
}

install_apt_deps() {
  if ! need_cmd apt-get; then
    echo "apt-get not found — install manually: python3 python3-venv curl git"
    return 0
  fi
  if ! need_cmd python3 || ! need_cmd curl; then
    echo "Installing system packages (may prompt for sudo)..."
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-venv python3-pip curl git ca-certificates
  fi
}

install_bun() {
  if need_cmd bun; then
    echo "Bun: $(bun --version)"
    return 0
  fi
  echo "Installing Bun..."
  curl -fsSL https://bun.sh/install | bash
  export BUN_INSTALL="${BUN_INSTALL:-$HOME/.bun}"
  export PATH="$BUN_INSTALL/bin:$PATH"
  if ! need_cmd bun; then
    echo "Bun install failed — add ~/.bun/bin to PATH and re-run." >&2
    exit 1
  fi
}

install_searxng() {
  if ! need_cmd docker; then
    echo "Docker not found — skipping SearXNG."
    echo "  Install Docker, then run: bash deploy/searxng/setup.sh"
    return 0
  fi
  if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon not running — skipping SearXNG."
    echo "  Start Docker, then run: bash deploy/searxng/setup.sh"
    return 0
  fi
  echo "Starting SearXNG (Docker)..."
  bash deploy/searxng/setup.sh
}

set_env_var() {
  local key="$1"
  local value="$2"
  local file="$3"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    echo "${key}=${value}" >>"$file"
  fi
}

remove_env_var() {
  local key="$1"
  local file="$2"
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    sed -i "/^${key}=/d" "$file"
  fi
}

repair_env() {
  local repairs=0
  if [[ ! -f .env ]]; then
    cp .env.example .env
    echo "Created .env from .env.example"
    repairs=$((repairs + 1))
  fi

  local llm_url searx_url cv_renderer bun_path
  llm_url="$(grep '^LLM_BASE_URL=' .env 2>/dev/null | cut -d= -f2- || true)"
  searx_url="$(grep '^SEARXNG_BASE_URL=' .env 2>/dev/null | cut -d= -f2- || true)"
  cv_renderer="$(grep '^CV_RENDERER=' .env 2>/dev/null | cut -d= -f2- || true)"
  bun_path="$(grep '^BUN_PATH=' .env 2>/dev/null | cut -d= -f2- || true)"

  if [[ -z "$llm_url" || "$llm_url" == *192.168.* ]]; then
    set_env_var "LLM_BASE_URL" "http://127.0.0.1:8006/v1" .env
    echo "Repaired LLM_BASE_URL → http://127.0.0.1:8006/v1"
    repairs=$((repairs + 1))
  fi
  if [[ -z "$searx_url" || "$searx_url" == *192.168.* ]]; then
    set_env_var "SEARXNG_BASE_URL" "http://127.0.0.1:8888" .env
    echo "Repaired SEARXNG_BASE_URL → http://127.0.0.1:8888"
    repairs=$((repairs + 1))
  fi
  if [[ -z "$cv_renderer" || "$cv_renderer" == "latex" ]]; then
    set_env_var "CV_RENDERER" "html" .env
    echo "Repaired CV_RENDERER → html"
    repairs=$((repairs + 1))
  fi
  if grep -q '^LLM_WAKE_' .env 2>/dev/null; then
    sed -i '/^LLM_WAKE_/d' .env
    echo "Removed legacy LLM_WAKE_* entries"
    repairs=$((repairs + 1))
  fi
  if [[ -z "$bun_path" && -x "${BUN_INSTALL:-$HOME/.bun}/bin/bun" ]]; then
    set_env_var "BUN_PATH" "${BUN_INSTALL:-$HOME/.bun}/bin/bun" .env
    echo "Set BUN_PATH"
    repairs=$((repairs + 1))
  fi

  if [[ $repairs -eq 0 ]]; then
    echo ".env OK"
  else
    echo "Repaired $repairs .env issue(s)"
  fi
}

install_apt_deps
install_bun

echo "=== Python virtualenv ==="
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "=== Portal scrapers (Bun) ==="
export PATH="${BUN_INSTALL:-$HOME/.bun}/bin:$PATH"
./install-skills.sh

echo "=== Playwright (HTML CV → PDF) ==="
bash scripts/install_playwright.sh

repair_env
install_searxng

echo ""
echo "=== Install complete ==="
echo "1. Point LLM_BASE_URL in .env to your OpenAI-compatible server (llama-server, Ollama, vLLM, OpenRouter, …)"
echo "2. Start the app:"
echo "     source .venv/bin/activate"
echo "     uvicorn app.main:app --host 0.0.0.0 --port 8080"
echo "3. Open http://localhost:8080/dashboard"
echo ""
echo "Full guide: SETUP.md"
