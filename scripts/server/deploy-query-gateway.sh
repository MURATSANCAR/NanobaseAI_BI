#!/usr/bin/env bash
# Deploy Query Gateway on production server (:8791).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP="${ROOT}/backend/query_gateway"
VENV="${ROOT}/backend/.venv"
ENV_FILE=/data/nanobaseai/bi/frontend/backend/query_gateway.env
UNIT=/etc/systemd/system/nanobase-query-gateway.service

log() { printf '[deploy-qg] %s\n' "$*"; }
die() { printf '[deploy-qg] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -x "${VENV}/bin/python" ]] || die "missing venv"

log "Installing query gateway deps (sqlglot, oracledb)"
if ! "${VENV}/bin/python" -c "import sqlglot, oracledb" 2>/dev/null; then
  if command -v uv >/dev/null; then
    uv pip install --python "${VENV}/bin/python" -r "${APP}/requirements.txt"
  elif "${VENV}/bin/python" -m ensurepip --upgrade >/dev/null 2>&1; then
    "${VENV}/bin/python" -m pip install -q -r "${APP}/requirements.txt"
  else
    die "cannot install requirements (no uv/pip)"
  fi
fi
# Ensure oracledb even if sqlglot already present
if ! "${VENV}/bin/python" -c "import oracledb" 2>/dev/null; then
  if command -v uv >/dev/null; then
    uv pip install --python "${VENV}/bin/python" 'oracledb>=2.0.0'
  else
    "${VENV}/bin/python" -m pip install -q 'oracledb>=2.0.0'
  fi
fi

umask 077
cat > "$ENV_FILE" <<EOF
QUERY_GATEWAY_PORT=8792
SECRETS_ROOT=/data/nanobaseai/bi/secrets
QG_STATEMENT_TIMEOUT_S=15
QG_MAX_LIMIT=500
QG_MAX_ROWS=500
PYTHONPATH=${ROOT}/backend
EOF
chmod 600 "$ENV_FILE"

sudo tee "$UNIT" >/dev/null <<UNIT
[Unit]
Description=Nanobase Query Gateway (sqlglot)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=administrator
WorkingDirectory=${ROOT}/backend
EnvironmentFile=${ENV_FILE}
Environment=PATH=${VENV}/bin:/usr/bin
Environment=PYTHONPATH=${ROOT}/backend
ExecStart=${VENV}/bin/uvicorn query_gateway.app:app --host 127.0.0.1 --port 8792
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable nanobase-query-gateway
sudo systemctl restart nanobase-query-gateway
sleep 2
curl -fsS http://127.0.0.1:8792/health | python3 -m json.tool
log "query gateway on :8792"
