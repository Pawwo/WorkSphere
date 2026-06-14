#!/usr/bin/env bash
# Rollback BC-250 LLM config from experiment snapshot.
set -euo pipefail

EXP_ID="${1:?usage: bc250_exp_rollback.sh EXP-NNN}"
SSH_HOST="${BC250_SSH:-root@192.168.0.112}"
SNAP_ROOT="${BC250_SNAP_ROOT:-/var/backups/bc250-snapshots}"
DEST="${SNAP_ROOT}/${EXP_ID}"

ssh -o ConnectTimeout=10 "$SSH_HOST" "bash -s" <<REMOTE
set -euo pipefail
DEST='$DEST'
if [[ ! -d "\$DEST" ]]; then
  echo "ERROR: snapshot not found: \$DEST" >&2
  exit 1
fi
systemctl stop llama-server-bielik llama-server-bielik-cpu 2>/dev/null || true
killall llama-server 2>/dev/null || true
sleep 2
[[ -f "\$DEST/llama-server-bielik.service" ]] && cp -a "\$DEST/llama-server-bielik.service" /etc/systemd/system/
[[ -f "\$DEST/llama-server-bielik-cpu.service" ]] && cp -a "\$DEST/llama-server-bielik-cpu.service" /etc/systemd/system/
[[ -f "\$DEST/bc250-llm-manager.py" ]] && cp -a "\$DEST/bc250-llm-manager.py" /usr/local/bin/
[[ -f "\$DEST/governor-config.toml" ]] && cp -a "\$DEST/governor-config.toml" /etc/cyan-skillfish-governor-smu/config.toml
[[ -f "\$DEST/default/grub" ]] && cp -a "\$DEST/default/grub" /etc/default/grub
[[ -f "\$DEST/ttm-gpu-memory.conf" ]] && cp -a "\$DEST/ttm-gpu-memory.conf" /etc/modprobe.d/
if [[ -d "\$DEST/lib" ]]; then
  cp -a "\$DEST/lib/"* /usr/local/lib/ 2>/dev/null || true
fi
ldconfig
if command -v restorecon >/dev/null; then
  restorecon -Rv /usr/local/lib/libggml-vulkan.so* /usr/local/bin/llama-server 2>/dev/null || true
fi
systemctl daemon-reload
systemctl start llama-server-bielik 2>/dev/null || systemctl start llama-server-bielik-cpu 2>/dev/null || true
echo "Rollback complete from \$DEST"
REMOTE

echo "Rolled back to $EXP_ID on $SSH_HOST"
