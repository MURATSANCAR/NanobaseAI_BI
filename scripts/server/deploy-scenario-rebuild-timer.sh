#!/usr/bin/env bash
# Install + enable recurring scenario pool rebuild timer on the BI host.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
API_ROOT="${NANOBASE_API_ROOT:-/data/nanobaseai/bi/frontend/backend}"
UNIT_DIR=/etc/systemd/system
SRC_UNIT="${ROOT}/infra/systemd/nanobase-scenario-rebuild.service"
SRC_TIMER="${ROOT}/infra/systemd/nanobase-scenario-rebuild.timer"

if [[ ! -f "$SRC_UNIT" || ! -f "$SRC_TIMER" ]]; then
  echo "missing unit files under infra/systemd" >&2
  exit 1
fi

# Ensure runner script is on the API host path
mkdir -p "${API_ROOT}/scripts"
install -m 0755 "${ROOT}/backend/scripts/run_scenario_pool_rebuild.py" \
  "${API_ROOT}/scripts/run_scenario_pool_rebuild.py"

# Env knobs (idempotent append)
ENV_FILE="${API_ROOT}/nanobase_api.env"
touch "$ENV_FILE"
grep -q '^SCENARIO_REBUILD_DATASOURCES=' "$ENV_FILE" 2>/dev/null || \
  echo 'SCENARIO_REBUILD_DATASOURCES=erp,sigorta' >>"$ENV_FILE"
grep -q '^SCENARIO_REBUILD_TENANT=' "$ENV_FILE" 2>/dev/null || \
  echo 'SCENARIO_REBUILD_TENANT=default' >>"$ENV_FILE"

sudo install -m 0644 "$SRC_UNIT" "${UNIT_DIR}/nanobase-scenario-rebuild.service"
sudo install -m 0644 "$SRC_TIMER" "${UNIT_DIR}/nanobase-scenario-rebuild.timer"
sudo systemctl daemon-reload
sudo systemctl enable nanobase-scenario-rebuild.timer
sudo systemctl start nanobase-scenario-rebuild.timer
systemctl status nanobase-scenario-rebuild.timer --no-pager -l || true
systemctl list-timers 'nanobase-scenario-rebuild*' --no-pager || true
echo "[deploy-scenario-rebuild-timer] timer enabled (boot+6h+02:15 daily)"
echo "Manual run: sudo systemctl start nanobase-scenario-rebuild.service"
