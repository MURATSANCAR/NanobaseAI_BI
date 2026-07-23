#!/usr/bin/env bash
# Install + enable continuous paraphrase expand timer on the BI host.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
API_ROOT="${NANOBASE_API_ROOT:-/data/nanobaseai/bi/frontend/backend}"
UNIT_DIR=/etc/systemd/system
SRC_UNIT="${ROOT}/infra/systemd/nanobase-paraphrase-expand.service"
SRC_TIMER="${ROOT}/infra/systemd/nanobase-paraphrase-expand.timer"

if [[ ! -f "$SRC_UNIT" || ! -f "$SRC_TIMER" ]]; then
  echo "missing unit files under infra/systemd" >&2
  exit 1
fi

mkdir -p "${API_ROOT}/scripts"
install -m 0755 "${ROOT}/backend/scripts/run_paraphrase_expand.py" \
  "${API_ROOT}/scripts/run_paraphrase_expand.py"
install -m 0755 "${ROOT}/backend/scripts/run_scenario_pool_rebuild.py" \
  "${API_ROOT}/scripts/run_scenario_pool_rebuild.py"

sudo install -m 0644 "$SRC_UNIT" "${UNIT_DIR}/nanobase-paraphrase-expand.service"
sudo install -m 0644 "$SRC_TIMER" "${UNIT_DIR}/nanobase-paraphrase-expand.timer"
sudo systemctl daemon-reload
sudo systemctl enable nanobase-paraphrase-expand.timer
sudo systemctl start nanobase-paraphrase-expand.timer
systemctl status nanobase-paraphrase-expand.timer --no-pager -l || true
systemctl list-timers 'nanobase-paraphrase-expand*' --no-pager || true
echo "[deploy-paraphrase-expand-timer] timer enabled (boot+2h cadence)"
echo "Manual run: sudo systemctl start nanobase-paraphrase-expand.service"
