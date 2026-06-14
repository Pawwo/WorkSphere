#!/usr/bin/env bash
# BC-250 LLM work profile: full CU + governor 1000–1500 MHz (→ ~900 mV under load).
set -euo pipefail

PERF_MODE="/usr/bin/cyan-skillfish-performance-mode"

if [[ -x "$PERF_MODE" ]]; then
  # Adaptive scaling: idle ~1000/800 MHz when model loaded but GPU quiet;
  # ramps to 1500/900 mV on inference (safe-point in governor config).
  "$PERF_MODE" --off 2>/dev/null || true
  "$PERF_MODE" --range 1000 1500 2>/dev/null || true
else
  CARD="/sys/class/drm/card0/device/power_dpm_force_performance_level"
  if [[ -w "$CARD" ]]; then
    echo performance >"$CARD" 2>/dev/null || echo auto >"$CARD" || true
  fi
fi

if [[ -x /usr/local/bin/bc250-cu-live-manager ]]; then
  /usr/local/bin/bc250-cu-live-manager --yes apply-service >/dev/null 2>&1 || true
fi
