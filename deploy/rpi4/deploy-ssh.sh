#!/usr/bin/env bash
set -euo pipefail

HOST="${WORKSPHERE_HOST:-192.168.0.194}"
USER="${WORKSPHERE_SSH_USER:-admin}"
PORT="${WORKSPHERE_SSH_PORT:-22}"
REMOTE_DIR="${WORKSPHERE_REMOTE_DIR:-/home/admin/worksphere}"

echo "Deploying to ${USER}@${HOST}:${REMOTE_DIR}"
ssh -p "$PORT" "${USER}@${HOST}" "cd ${REMOTE_DIR} && bash deploy/rpi4/remote-deploy.sh"
