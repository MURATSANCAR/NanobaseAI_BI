#!/usr/bin/env bash
# Semantic Layer V1 for the TİMAŞ cockpit:
#   package  : backend/semantic_layer (catalog + evidence engine + history miner + resolver + compilers)
#   service  : backend/semantic_bridge (FastAPI :8795) — cockpit contract (/api/v1/ask, /run_sql, /engine) + /api/v1/semantic/*
#   store    : bi_meta PostgreSQL (sl_* tables, alembic 014) — shared with nanobase_api portal pages
#   worker   : nightly pipeline (profile → mine → docs → certify → version) via systemd timer
# Steps: migrate → venv deps → offline pipeline (profile from SQL Server) → bridge unit → health/ask smoke.
set -euo pipefail
export SYSTEMD_BUS_TIMEOUT="${SYSTEMD_BUS_TIMEOUT:-300}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${SEMANTIC_VENV:-/data/nanobaseai/bi/frontend/backend/.venv}"
KNOWLEDGE="${SEMANTIC_KNOWLEDGE_DIR:-${ROOT}/configs/semantic/knowledge/logo}"   # operator docs + validated pairs
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
CONN_FILE="${SEMANTIC_CONNECTION_FILE:-${SECRETS}/logo-mssql-connection.json}"
API_ENV="${NANOBASE_API_ENV:-/data/nanobaseai/bi/frontend/backend/nanobase_api.env}"
ENV_FILE="${SEMANTIC_BRIDGE_ENV:-/data/nanobaseai/bi/frontend/backend/nanobase_semantic_bridge.env}"
UNIT=/etc/systemd/system/nanobase-semantic-bridge.service
PORT="${SEMANTIC_BRIDGE_PORT:-8795}"
WORKERS="${SEMANTIC_BRIDGE_WORKERS:-2}"

log() { printf '[deploy-semantic-bridge] %s\n' "$*"; }
die() { printf '[deploy-semantic-bridge] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -x "${VENV}/bin/python" ]] || die "missing venv ${VENV}"
[[ -f "$CONN_FILE" ]] || die "missing connection file ${CONN_FILE} — write it from ${SECRETS}/mssql-ro.datasources.json (mode 600)"

# --- 0. deps + migration (sl_* tables in bi_meta) ------------------------------------------------
log "installing deps"
"${VENV}/bin/python" -m pip install -q -r "${ROOT}/backend/semantic_bridge/requirements.txt"
log "alembic upgrade head (014_semantic_layer)"
"${ROOT}/scripts/server/migrate-nanobase-api.sh"

# --- 1. env file (never printed) ----------------------------------------------------------------
if [[ -z "${NANOBASE_META_DSN:-}" ]]; then
  META_PW="$(tr -d '\n\r' < "${SECRETS}/bi-meta-db.password")"
  META_PW_ENC="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote_plus(sys.argv[1]))" "$META_PW")"
  NANOBASE_META_DSN="postgresql+psycopg2://bi_meta:${META_PW_ENC}@127.0.0.1:5434/bi_meta"
fi
LLM_BASE="$(grep -E '^OPENAI_API_BASE=' "$API_ENV" | cut -d= -f2- | tr -d '"' || true)"
LLM_MODEL="$(grep -E '^LLM_MODEL_NAME=' "$API_ENV" | cut -d= -f2- | tr -d '"' || true)"
umask 077
cat > "$ENV_FILE" <<ENV
SEMANTIC_STORE_DSN=${NANOBASE_META_DSN}
SEMANTIC_TENANT_ID=default
SEMANTIC_DATASOURCE_ID=logo
SEMANTIC_KNOWLEDGE_DIR=${KNOWLEDGE}
SEMANTIC_CONNECTION_FILE=${CONN_FILE}
# Operator scope for this deployment (all optional; empty = whole schema, connector defaults):
SEMANTIC_SCHEMA=${SEMANTIC_SCHEMA:-dbo}
SEMANTIC_TABLE_LIKE=${SEMANTIC_TABLE_LIKE:-}
# Table-name placeholders are discovered from the names themselves (LG_411_01_X → LG_{n0}_{n1}_X).
# SEMANTIC_CONTEXT overrides them at compile time (next period without touching the catalog),
# SEMANTIC_PATTERN_LABELS only renames them for the portal.
SEMANTIC_CONTEXT=${SEMANTIC_CONTEXT:-}
SEMANTIC_PATTERN_LABELS=${SEMANTIC_PATTERN_LABELS:-}
SEMANTIC_DEFAULT_PERIOD=${SEMANTIC_DEFAULT_PERIOD:-}
SEMANTIC_DIALECT=${SEMANTIC_DIALECT:-}
SEMANTIC_MIN_SUPPORT=3
SEMANTIC_RECALL=1
SEMANTIC_STRICT_MISS=0
SEMANTIC_SUMMARY_MODE=fast
SEMANTIC_MAX_ROWS=500
OPENAI_API_BASE=${LLM_BASE:-http://172.17.0.1:8020/v1}
OPENAI_API_KEY=
LLM_MODEL_NAME=${LLM_MODEL:-nanobaseai-bi-llm}
LLM_TIMEOUT_SEC=240
ENV
chmod 600 "$ENV_FILE"

# --- 2. offline pipeline: profile live SQL Server, mine knowledge, certify ------------------------
log "pipeline (profile → mine → docs → certify)"
set -a; source "$ENV_FILE"; set +a
cd "${ROOT}/backend"
PYTHONPATH="${ROOT}/backend" "${VENV}/bin/python" -m semantic_layer.cli pipeline --note "deploy $(date -Is)" | tail -40
PYTHONPATH="${ROOT}/backend" "${VENV}/bin/python" -m semantic_layer.cli status

# --- 3. bridge service ----------------------------------------------------------------------------
log "writing ${UNIT}"
sudo tee "$UNIT" >/dev/null <<UNITEOF
[Unit]
Description=NanobaseAI Semantic Bridge (:${PORT}) — cockpit NL→SQL
After=network-online.target
Wants=network-online.target

[Service]
User=administrator
WorkingDirectory=${ROOT}/backend
EnvironmentFile=${ENV_FILE}
Environment=PYTHONPATH=${ROOT}/backend
ExecStart=${VENV}/bin/uvicorn semantic_bridge.app:app --host 127.0.0.1 --port ${PORT} --workers ${WORKERS} --timeout-keep-alive 30
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNITEOF
sudo cp "${ROOT}/infra/systemd/nanobase-semantic-worker.service" "${ROOT}/infra/systemd/nanobase-semantic-worker.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nanobase-semantic-bridge.service nanobase-semantic-worker.timer
sudo systemctl restart nanobase-semantic-bridge.service
sleep 3
curl -fsS -m 20 "http://127.0.0.1:${PORT}/health" | head -c 400; echo
log "ask smoke"
curl -fsS -m 240 -H 'Content-Type: application/json' -d '{"question":"2026 toplam net ciro nedir?","sampleSize":5}' "http://127.0.0.1:${PORT}/api/v1/ask" | head -c 600; echo
log "done — switch nginx: scripts/server/switch-timas-api.sh semantic   (back: bridge)"
