#!/usr/bin/env bash
# Install + systemd for nanobase_api on the production server.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_DIR="${ROOT}/backend/nanobase_api"
VENV="${ROOT}/backend/.venv"
SECRETS=/data/nanobaseai/bi/secrets
UNIT=/etc/systemd/system/nanobase-bi-api.service

log() { printf '[deploy-nanobase-api] %s\n' "$*"; }
die() { printf '[deploy-nanobase-api] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -d "$VENV" ]] || { echo "missing $VENV"; exit 1; }

log "Checking API deps in shared backend venv"
if ! "${VENV}/bin/python" -c "import fastapi,uvicorn,httpx,sqlalchemy,psycopg2" 2>/dev/null; then
  if "${VENV}/bin/python" -m ensurepip --upgrade >/dev/null 2>&1; then
    "${VENV}/bin/python" -m pip install -q -r "${APP_DIR}/requirements.txt"
  elif command -v uv >/dev/null; then
    uv pip install --python "${VENV}/bin/python" -r "${APP_DIR}/requirements.txt"
  else
    die "Missing deps and no pip/uv to install ${APP_DIR}/requirements.txt"
  fi
fi

META_PW="$(tr -d '\n\r' < "${SECRETS}/bi-meta-db.password")"
META_PW_ENC="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote_plus(sys.argv[1]))" "$META_PW")"
ENV_FILE=/data/nanobaseai/bi/frontend/backend/nanobase_api.env
umask 077
cat > "$ENV_FILE" <<EOF
NANOBASE_API_PORT=8790
NANOBASE_META_DSN=postgresql+psycopg2://bi_meta:${META_PW_ENC}@127.0.0.1:5434/bi_meta
DBGPT_BASE=http://127.0.0.1:5670
LLM_MODEL_NAME=nanobase-qwen36-35b-a3b-mtp
NANOBASE_ACTIVE_DB=bi_reporting
PYTHONPATH=${ROOT}/backend
EOF
chmod 600 "$ENV_FILE"

sudo tee "$UNIT" >/dev/null <<UNIT
[Unit]
Description=Nanobase BI API (FastAPI)
After=network.target nanobase-dbgpt.service
Wants=nanobase-dbgpt.service

[Service]
Type=simple
User=administrator
WorkingDirectory=${ROOT}/backend
EnvironmentFile=-${ROOT}/backend/.env
EnvironmentFile=${ENV_FILE}
Environment=PATH=${VENV}/bin:/usr/bin
Environment=PYTHONPATH=${ROOT}/backend
ExecStart=${VENV}/bin/uvicorn nanobase_api.app:app --host 127.0.0.1 --port 8790
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable nanobase-bi-api
sudo systemctl restart nanobase-bi-api
sleep 2
curl -fsS http://127.0.0.1:8790/health | python3 -m json.tool
curl -fsS http://127.0.0.1:8790/api/v1/bi/sources | python3 -c 'import sys,json; d=json.load(sys.stdin); print("sources", len(d.get("sources") or []), "active", d.get("active_id"))'
log "nanobase-bi-api active on :8790 (bridge :8789 unchanged)"
