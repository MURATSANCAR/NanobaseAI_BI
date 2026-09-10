#!/usr/bin/env bash
# Wire the Forecast API (:8793) into nanobase_api: env keys, alembic 013 (fc_forecast_run/point),
# restart API + ARQ worker, verify /health of both services. Idempotent.
set -euo pipefail
# Shared host: systemd's manager can take >25 s to answer; keep systemctl from timing out.
export SYSTEMD_BUS_TIMEOUT="${SYSTEMD_BUS_TIMEOUT:-300}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${NANOBASE_API_ENV:-/data/nanobaseai/bi/frontend/backend/nanobase_api.env}"
FORECAST_BASE="${FORECAST_API_BASE:-http://127.0.0.1:8793}"

log() { printf '[enable-forecast-chat] %s\n' "$*"; }
die() { printf '[enable-forecast-chat] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE"
[[ -d "${ROOT}/backend/forecasting" ]] || die "missing ${ROOT}/backend/forecasting (rsync the repo first)"

set_kv() {  # set_kv KEY VALUE — replace or append
  local k="$1" v="$2"
  if grep -q "^${k}=" "$ENV_FILE"; then
    sed -i "s|^${k}=.*|${k}=${v}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$k" "$v" >> "$ENV_FILE"
  fi
}
set_kv FORECAST_API_BASE "$FORECAST_BASE"
set_kv FORECAST_CHAT_ENABLED true
log "env: $(grep -E '^FORECAST_' "$ENV_FILE" | tr '\n' ' ')"

log "Forecast service health"
curl -fsS "${FORECAST_BASE}/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(" ", d.get("default_engine"), "ready" if d.get("ready") else "NOT READY", d.get("error") or "")' \
  || die "forecast service at ${FORECAST_BASE} is not ready — run scripts/server/deploy-forecast.sh first"

log "Alembic migrations (013 forecast tables)"
"${ROOT}/scripts/server/migrate-nanobase-api.sh"

log "Restarting nanobase-bi-api + nanobase-arq"
sudo -E systemctl restart nanobase-bi-api
sudo -E systemctl restart nanobase-arq
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8790/health >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS http://127.0.0.1:8790/health | python3 -m json.tool | head -20
systemctl is-active nanobase-bi-api nanobase-arq nanobase-forecast
log "forecast chat branch enabled (FORECAST_CHAT_ENABLED=true → chat_gateway forecast intent before the LLM path)"
