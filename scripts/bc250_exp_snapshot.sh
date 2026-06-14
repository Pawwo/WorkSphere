#!/usr/bin/env bash
# Snapshot BC-250 LLM config before a tuning experiment (run on server or via ssh).
set -euo pipefail

EXP_ID="${1:?usage: bc250_exp_snapshot.sh EXP-NNN}"
SSH_HOST="${BC250_SSH:-root@192.168.0.112}"
SNAP_ROOT="${BC250_SNAP_ROOT:-/var/backups/bc250-snapshots}"
DEST="${SNAP_ROOT}/${EXP_ID}"

run_remote() {
  ssh -o ConnectTimeout=10 "$SSH_HOST" "$@"
}

run_remote "mkdir -p '$DEST'"

run_remote "bash -s" <<REMOTE
set -euo pipefail
DEST='$DEST'
cp -a /etc/systemd/system/llama-server-bielik.service "\$DEST/" 2>/dev/null || true
cp -a /etc/systemd/system/llama-server-bielik-cpu.service "\$DEST/" 2>/dev/null || true
cp -a /usr/local/bin/bc250-llm-manager.py "\$DEST/" 2>/dev/null || true
cp -a /etc/cyan-skillfish-governor-smu/config.toml "\$DEST/governor-config.toml" 2>/dev/null || true
cp -a /etc/default/grub "\$DEST/" 2>/dev/null || true
cp -a /etc/modprobe.d/ttm-gpu-memory.conf "\$DEST/" 2>/dev/null || true
mkdir -p "\$DEST/lib"
cp -a /usr/local/lib/libggml-vulkan.so* "\$DEST/lib/" 2>/dev/null || true
cp -a /usr/local/lib/libllama-server-impl.so* "\$DEST/lib/" 2>/dev/null || true
if [[ -d /workspace/llama.cpp/.git ]]; then
  git -C /workspace/llama.cpp rev-parse HEAD > "\$DEST/llama_cpp_commit.txt"
  git -C /workspace/llama.cpp status --short > "\$DEST/llama_cpp_status.txt" || true
fi
/usr/local/bin/llama-server --version 2>/dev/null | head -2 > "\$DEST/llama_version.txt" || true
ls -la /usr/local/lib/libggml-vulkan.so* > "\$DEST/libggml_sizes.txt" 2>/dev/null || true
nm -D /usr/local/lib/libggml-vulkan.so.0.14.0 2>/dev/null | grep -c ' U matmul' > "\$DEST/undef_matmul.txt" || echo 0 > "\$DEST/undef_matmul.txt"
date -Iseconds > "\$DEST/snapshot_time.txt"
echo "$EXP_ID" > "\$DEST/exp_id.txt"
REMOTE

echo "Snapshot saved: $SSH_HOST:$DEST"
