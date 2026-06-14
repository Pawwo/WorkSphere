#!/usr/bin/env bash
# Run BC-250 LLM gates after a tuning experiment. On FAIL, optionally rollback.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXP_ID="${1:-exp-000}"
GATE="${2:-AB}"
ROLLBACK_ON_FAIL="${BC250_ROLLBACK_ON_FAIL:-1}"
BASELINE_TG="${BC250_BASELINE_TG:-}"

args=(--exp "$EXP_ID" --gate "$GATE")
[[ -n "$BASELINE_TG" ]] && args+=(--baseline-tg "$BASELINE_TG")

if ! python3 "$ROOT/scripts/bc250_llm_gate.py" "${args[@]}"; then
  echo "GATE FAIL for $EXP_ID"
  if [[ "$ROLLBACK_ON_FAIL" == "1" ]] && [[ "$EXP_ID" != "exp-000" ]]; then
    prev="${EXP_ID%???}"
    # rollback to previous snapshot if exists — caller should pass snapshot id
    if [[ -n "${BC250_ROLLBACK_TO:-}" ]]; then
      echo "Rolling back to ${BC250_ROLLBACK_TO}..."
      "$ROOT/scripts/bc250_exp_rollback.sh" "$BC250_ROLLBACK_TO"
    fi
  fi
  exit 1
fi
echo "GATE PASS for $EXP_ID"
