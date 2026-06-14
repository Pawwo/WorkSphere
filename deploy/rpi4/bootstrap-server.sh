#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${WORKSPHERE_REPO_URL:-https://github.com/Pawwo/WorkSphere.git}"
HOST="${WORKSPHERE_HOST:-192.168.0.194}"
USER="${WORKSPHERE_SSH_USER:-admin}"
PORT="${WORKSPHERE_SSH_PORT:-22}"
REMOTE_DIR="${WORKSPHERE_REMOTE_DIR:-/home/admin/worksphere}"

echo "Bootstrap ${USER}@${HOST}:${REMOTE_DIR} from ${REPO_URL}"

ssh -p "$PORT" "${USER}@${HOST}" "bash -s" -- "$REPO_URL" "$REMOTE_DIR" <<'REMOTE'
set -euo pipefail
REPO_URL="$1"
DIR="$2"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${HOME}/worksphere-backup-${STAMP}"

if [[ -d "$DIR" ]]; then
  echo "Backing up existing install to $BACKUP"
  mkdir -p "$BACKUP"
  [[ -f "$DIR/.env" ]] && cp -a "$DIR/.env" "$BACKUP/"
  [[ -d "$DIR/data" ]] && cp -a "$DIR/data" "$BACKUP/"
  sudo systemctl stop worksphere 2>/dev/null || true
  mv "$DIR" "${DIR}.old-${STAMP}"
fi

git clone "$REPO_URL" "$DIR"
cd "$DIR"

if [[ -d "$BACKUP" ]]; then
  [[ -f "$BACKUP/.env" ]] && cp -a "$BACKUP/.env" .env
  if [[ -d "$BACKUP/data" ]]; then
    mkdir -p data
    cp -a "$BACKUP/data/." data/
  fi
fi

bash deploy/rpi4/install.sh
sudo cp deploy/rpi4/worksphere.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now worksphere
sleep 3
curl -sf http://127.0.0.1:8080/health >/dev/null
git describe --tags --always > .deployed-version
echo "Bootstrap OK — $(cat .deployed-version)"
REMOTE
