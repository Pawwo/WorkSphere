#!/bin/bash
# Start SearXNG via Docker (requires docker compose).
set -euo pipefail
cd "$(dirname "$0")"
docker compose pull
docker compose up -d
sleep 4
curl -sf "http://127.0.0.1:8888/search?q=test&format=json" | head -c 200
echo
echo "SearXNG ready at http://127.0.0.1:8888"
