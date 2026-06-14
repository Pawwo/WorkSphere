#!/usr/bin/env bash
# Apply BC-250 checklist gaps: env, TTM modprobe, CPU governor, drirc, mesa-utils.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

mkdir -p /etc/environment.d
install -m 0644 "$SCRIPT_DIR/etc-environment.d/llm-vulkan.conf" /etc/environment.d/llm-vulkan.conf
install -m 0644 "$SCRIPT_DIR/modprobe.d/ttm-gpu-memory.conf" /etc/modprobe.d/ttm-gpu-memory.conf
install -m 0644 "$SCRIPT_DIR/tmpfiles.d/cpu-governor.conf" /etc/tmpfiles.d/cpu-governor.conf
install -m 0644 "$SCRIPT_DIR/drirc" /etc/drirc

# Merge into /etc/environment for shells without environment.d (headless SSH)
ENV_FILE=/etc/environment
for key in AMD_VULKAN_ICD RADV_DEBUG GGML_VK_FORCE_MAX_ALLOCATION_SIZE; do
  line="$(grep "^${key}=" "$SCRIPT_DIR/etc-environment.d/llm-vulkan.conf" || true)"
  if [[ -n "$line" ]]; then
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      sed -i "s|^${key}=.*|${line}|" "$ENV_FILE"
    else
      echo "$line" >> "$ENV_FILE"
    fi
  fi
done

# Fedora: glxinfo is in glx-utils (Debian/Ubuntu: mesa-utils)
dnf install -y glx-utils spirv-tools glslc

# BC-250 often has no cpufreq sysfs (mining board); rule is harmless if path missing
if [[ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]]; then
  systemd-tmpfiles --create /etc/tmpfiles.d/cpu-governor.conf
else
  echo "note: no cpufreq scaling_governor on this CPU — step 10 N/A (Zen2 runs at hardware P-states)"
fi

# Drop stale TTM modprobe if it conflicts with ttm-gpu-memory.conf
if [[ -f /etc/modprobe.d/ttm.conf ]] && grep -q "3776000" /etc/modprobe.d/ttm.conf 2>/dev/null; then
  mv /etc/modprobe.d/ttm.conf /etc/modprobe.d/ttm.conf.bak.3776000
fi

# Runtime TTM (until next boot picks up modprobe + dracut)
if [[ -w /sys/module/ttm/parameters/pages_limit ]]; then
  echo 3959290 > /sys/module/ttm/parameters/pages_limit
  echo 3959290 > /sys/module/ttm/parameters/page_pool_size
fi

dracut -f

echo "=== verify ==="
rpm -q glx-utils cyan-skillfish-governor-smu
# Headless: glxinfo needs Xvfb; GPU compute uses vulkaninfo (RADV), not GLX
if command -v Xvfb >/dev/null; then
  dnf install -y xorg-x11-server-Xvfb 2>/dev/null || true
  Xvfb :99 -screen 0 1x1x24 &>/dev/null & XVFB_PID=$!
  sleep 1
  DISPLAY=:99 glxinfo -B 2>/dev/null | grep "OpenGL version" || true
  kill "$XVFB_PID" 2>/dev/null || true
fi
vulkaninfo --summary 2>/dev/null | grep "deviceName" | head -1
systemctl is-active cyan-skillfish-governor-smu
if [[ -f /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor ]]; then
  cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor
else
  echo "cpufreq: N/A (no scaling driver)"
fi
cat /sys/module/ttm/parameters/pages_limit
grep -E "AMD_VULKAN|RADV|GGML_VK" /etc/environment
cat /etc/modprobe.d/ttm-gpu-memory.conf

echo "Done. TTM modprobe change needs: dracut -f && reboot"
