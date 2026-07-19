#!/usr/bin/env bash
# systemd unit for ARQ schema-scan worker
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${ROOT}/backend/.venv"
UNIT=/etc/systemd/system/nanobase-arq.service
ENV_FILE=/data/nanobaseai/bi/frontend/backend/nanobase_api.env

sudo tee "$UNIT" >/dev/null <<UNIT
[Unit]
Description=Nanobase ARQ schema-scan worker
After=network.target redis-server.service
Wants=network-online.target

[Service]
Type=simple
User=administrator
WorkingDirectory=${ROOT}/backend
EnvironmentFile=-${ROOT}/backend/.env
EnvironmentFile=-${ENV_FILE}
Environment=PATH=${VENV}/bin:/usr/bin
Environment=PYTHONPATH=${ROOT}/backend
Environment=REDIS_URL=redis://127.0.0.1:6379/0
Environment=ARQ_ENABLED=1
ExecStart=${VENV}/bin/arq nanobase_api.infrastructure.arq_worker.WorkerSettings
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable nanobase-arq
sudo systemctl restart nanobase-arq
sleep 1
systemctl is-active nanobase-arq
echo "[deploy-arq] nanobase-arq active"
