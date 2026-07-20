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

log "Installing API deps in shared backend venv"
if "${VENV}/bin/python" -m ensurepip --upgrade >/dev/null 2>&1; then
  "${VENV}/bin/python" -m pip install -q -r "${APP_DIR}/requirements.txt"
elif command -v uv >/dev/null; then
  uv pip install --python "${VENV}/bin/python" -r "${APP_DIR}/requirements.txt"
else
  die "Missing pip/uv to install ${APP_DIR}/requirements.txt"
fi

META_PW="$(tr -d '\n\r' < "${SECRETS}/bi-meta-db.password")"
META_PW_ENC="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote_plus(sys.argv[1]))" "$META_PW")"
ENV_FILE=/data/nanobaseai/bi/frontend/backend/nanobase_api.env
# Keep operator overlays (Superset, embed key, etc.) across redeploys
PRESERVE_ENV="$(mktemp)"
if [[ -f "$ENV_FILE" ]]; then
  grep -E '^(BI_SUPERSET_|BI_EMBED_API_KEY|OPENAI_API_KEY|BI_SOURCES_FILE)=' "$ENV_FILE" >"$PRESERVE_ENV" || true
fi
umask 077
cat > "$ENV_FILE" <<EOF
NANOBASE_API_PORT=8790
NANOBASE_META_DSN=postgresql+psycopg2://bi_meta:${META_PW_ENC}@127.0.0.1:5434/bi_meta
DBGPT_BASE=http://127.0.0.1:5670
LLM_MODEL_NAME=nanobase-qwen36-35b-a3b-mtp
NANOBASE_ACTIVE_DB=bi_reporting
QUERY_GATEWAY_BASE=http://127.0.0.1:8792
PYTHONPATH=${ROOT}/backend
AUTH_MODE=dev
DEV_TENANT_ID=default
NANOBASE_TEXT2SQL_EXECUTION_MODE=QUERY_GATEWAY
ARQ_ENABLED=1
REDIS_URL=redis://127.0.0.1:6379/0
SCHEMA_INDEXER_ROOT=${ROOT}/tools/schema-indexer
NANOBASE_PYTHON=${VENV}/bin/python
SECRETS_ROOT=${SECRETS}
BI_EMBED_URL=http://127.0.0.1:8083/v1/embeddings
QDRANT_URL=http://127.0.0.1:6333
TEXT2SQL_PREFER=chat
TEXT2SQL_FALLBACK_TO_CHAT=1
LLM_TIMEOUT_SEC=300
MODEL_QUEUE_TIMEOUT=360
MODEL_QUEUE_LIMIT=100
EOF
# Prefer shared contract embedding key when present (BGE-M3 :8083)
if [[ -z "${BI_EMBED_API_KEY:-}" ]]; then
  # Reuse previously deployed key first
  if [[ -s "$PRESERVE_ENV" ]]; then
    BI_EMBED_API_KEY="$(grep -E '^BI_EMBED_API_KEY=' "$PRESERVE_ENV" | head -1 | cut -d= -f2- | tr -d '\"\r')"
  fi
fi
if [[ -z "${BI_EMBED_API_KEY:-}" ]]; then
  for cand in \
    "${ROOT}/backend/.env" \
    /data/nanobaseai/mobile-qa/contract-intelligence/embedding-service/.env \
    /data/nanobaseai/bi/secrets/embed-api.key; do
    if [[ -f "$cand" ]]; then
      BI_EMBED_API_KEY="$(grep -E '^(BI_EMBED_API_KEY|API_KEY|OPENAI_API_KEY)=' "$cand" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\"\r')"
      [[ -n "$BI_EMBED_API_KEY" ]] && break
    fi
  done
fi
if [[ -n "${BI_EMBED_API_KEY:-}" ]]; then
  printf 'BI_EMBED_API_KEY=%s\n' "$BI_EMBED_API_KEY" >> "$ENV_FILE"
else
  log "WARN: BI_EMBED_API_KEY unset — schema retrieve will fail until set"
fi
# Restore preserved overlays (skip BI_EMBED_API_KEY if already written)
if [[ -s "$PRESERVE_ENV" ]]; then
  while IFS= read -r line; do
    k="${line%%=*}"
    [[ "$k" == "BI_EMBED_API_KEY" ]] && grep -q '^BI_EMBED_API_KEY=' "$ENV_FILE" && continue
    printf '%s\n' "$line" >> "$ENV_FILE"
  done <"$PRESERVE_ENV"
  log "Restored preserved env overlays from prior nanobase_api.env"
fi
rm -f "$PRESERVE_ENV"
chmod 600 "$ENV_FILE"

log "Running Alembic migrations"
"${ROOT}/scripts/server/migrate-nanobase-api.sh"

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
