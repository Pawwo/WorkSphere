#!/bin/bash
# Run on host with Docker (e.g. admin@192.168.0.194)
set -euo pipefail
cd "$(dirname "$0")"
docker compose pull
docker compose up -d
sleep 4
curl -sf "http://127.0.0.1:8888/search?q=test&format=json" | head -c 200
echo
echo "SearXNG: http://$(hostname -I | awk '{print $1}'):8888"
