#!/bin/bash
# Run ON BC-250 (192.168.0.112) as root.
# Jina Embeddings v3 GGUF + retrieval LoRAs via llama-server on :8007.
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/root/models/jina}"
REPO="gaianet/jina-embeddings-v3-GGUF"
UNIT="/etc/systemd/system/llama-server-jina-embed.service"
# CPU-only: avoids Vulkan contention with llama-server-bielik on :8006
NGL="${JINA_NGL:-0}"

mkdir -p "$MODEL_DIR"
cd "$MODEL_DIR"

if [[ ! -f jina-embeddings-v3-Q4_K_M.gguf ]]; then
  echo "Downloading jina-embeddings-v3-Q4_K_M.gguf..."
  hf download "$REPO" jina-embeddings-v3-Q4_K_M.gguf --local-dir .
fi
if [[ ! -f lora-retrieval.query-jina-embeddings-v3-f16.gguf ]]; then
  echo "Downloading retrieval LoRAs..."
  hf download "$REPO" \
    lora-retrieval.query-jina-embeddings-v3-f16.gguf \
    lora-retrieval.passage-jina-embeddings-v3-f16.gguf \
    --local-dir .
fi

cat > "$UNIT" <<EOF
[Unit]
Description=llama-server Jina Embeddings v3 (retrieval) for RAG on LAN
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
ExecStart=/usr/local/bin/llama-server \\
  -m ${MODEL_DIR}/jina-embeddings-v3-Q4_K_M.gguf \\
  -ngl ${NGL} \\
  -c 8192 \\
  -np 1 \\
  --threads 6 \\
  --batch-size 512 \\
  --ubatch-size 512 \\
  --host 0.0.0.0 \\
  --port 8007 \\
  --embeddings \\
  --pooling cls \\
  --lora ${MODEL_DIR}/lora-retrieval.query-jina-embeddings-v3-f16.gguf,${MODEL_DIR}/lora-retrieval.passage-jina-embeddings-v3-f16.gguf
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=llama-server-jina-embed

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable llama-server-jina-embed.service
systemctl restart llama-server-jina-embed.service

if command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-port=8007/tcp 2>/dev/null || true
  firewall-cmd --reload 2>/dev/null || true
fi

sleep 3
if curl -sf --max-time 10 "http://127.0.0.1:8007/v1/models" >/dev/null; then
  echo "OK: Jina embeddings http://$(hostname -I | awk '{print $1}'):8007/v1"
  curl -sf "http://127.0.0.1:8007/v1/models" | head -c 400
  echo
else
  echo "WARN: service started but /v1/models not ready — check journalctl -u llama-server-jina-embed"
  systemctl status llama-server-jina-embed --no-pager || true
  exit 1
fi
