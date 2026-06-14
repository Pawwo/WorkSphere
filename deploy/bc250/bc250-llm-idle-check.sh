#!/usr/bin/env bash
# Stop LLM after idle period (hybrid power profile).
set -euo pipefail
IDLE_MINUTES="${BC250_LLM_IDLE_MINUTES:-50}"
ACTIVITY_FILE="/var/run/bc250-llm.last_activity"

LLM_UNIT="${BC250_LLM_UNIT:-llama-server-bielik}"
if ! systemctl is-active --quiet "$LLM_UNIT"; then
  exit 0
fi

now=$(date +%s)
last=$now
if [[ -f "$ACTIVITY_FILE" ]]; then
  last=$(cat "$ACTIVITY_FILE" 2>/dev/null || echo "$now")
fi
idle_sec=$((now - last))
limit_sec=$((IDLE_MINUTES * 60))
if (( idle_sec < limit_sec )); then
  exit 0
fi

if ss -tn state established "( sport = :8006 )" 2>/dev/null | grep -q ESTAB; then
  date +%s >"$ACTIVITY_FILE"
  exit 0
fi

curl -sf -X POST http://127.0.0.1:8099/sleep >/dev/null \
  || systemctl stop "$LLM_UNIT" llama-server-bielik llama-server-jina-embed
