#!/usr/bin/env bash
# BC-250 deep idle: minimal GPU clocks when LLM is stopped.
set -euo pipefail

PERF_MODE="/usr/bin/cyan-skillfish-performance-mode"

if [[ -x "$PERF_MODE" ]]; then
  "$PERF_MODE" --off 2>/dev/null || true
  "$PERF_MODE" --range 500 1000 2>/dev/null || true
else
  CARD="/sys/class/drm/card0/device/power_dpm_force_performance_level"
  if [[ -w "$CARD" ]]; then
    echo auto >"$CARD" 2>/dev/null || true
  fi
fi
