#!/usr/bin/env bash
# Semantic Layer V1 for the TİMAŞ cockpit:
#   package : backend/semantic_layer (catalog + evidence engine + history miner + resolver + compilers)
#   service : backend/semantic_bridge (FastAPI :8795) — cockpit contract + /api/v1/semantic/* + /api/v1/schema/*
#   store   : bi_meta PostgreSQL (sl_* tables, alembic 014) — shared with the portal pages
#   worker  : nightly pipeline (profile → mine → docs → certify → version) via systemd timer
#
# The code must already be on the box (this repo is rsynced, not cloned):
#   rsync -a --delete --exclude node_modules --exclude .git ./ nanobase-direct:/data/nanobaseai/bi/frontend/
#
# Own virtualenv on purpose: the API venv (/…/backend/.venv) runs production nanobase-bi-api and is never
# touched here. The portal only needs what that venv already has (sqlalchemy, sqlglot, pyyaml, httpx);
# the database driver (pyodbc) lives with the bridge.
set -euo pipefail
export SYSTEMD_BUS_TIMEOUT="${SYSTEMD_BUS_TIMEOUT:-300}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${SEMANTIC_VENV:-/data/nanobaseai/bi/semantic-venv}"
API_VENV="${NANOBASE_API_VENV:-${ROOT}/backend/.venv}"
KNOWLEDGE="${SEMANTIC_KNOWLEDGE_DIR:-${ROOT}/configs/semantic/knowledge/logo}"
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
CONN_FILE="${SEMANTIC_CONNECTION_FILE:-${SECRETS}/logo-mssql-connection.json}"
DATASOURCE_KEY="${SEMANTIC_DATASOURCE_KEY:-logo}"
API_ENV="${NANOBASE_API_ENV:-${ROOT}/backend/nanobase_api.env}"
# Outside the rsynced code tree on purpose: `rsync --delete` of the repo must not delete the file both
# units load, and it holds a database password that must never be near the repository.
ENV_FILE="${SEMANTIC_BRIDGE_ENV:-/etc/nanobase/semantic-bridge.env}"
UNIT=/etc/systemd/system/nanobase-semantic-bridge.service
PORT="${SEMANTIC_BRIDGE_PORT:-8795}"
WORKERS="${SEMANTIC_BRIDGE_WORKERS:-1}"
# Interpreter: whatever this box actually has (3.10+). Prefer an explicit choice, then the newest
# system Python, and finally the API venv's own base — never a hard-coded minor version.
PYTHON_BIN="${SEMANTIC_PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON_BIN="$candidate"; break; fi
  done
fi
[[ -n "$PYTHON_BIN" && -x "${API_VENV}/bin/python" ]] || true
[[ -n "$PYTHON_BIN" ]] || PYTHON_BIN="${API_VENV}/bin/python"

log() { printf '[deploy-semantic-bridge] %s\n' "$*"; }
die() { printf '[deploy-semantic-bridge] ERROR: %s\n' "$*" >&2; exit 1; }

# Result snapshots and conversation state are process-local until a shared store is implemented.
[[ "$WORKERS" == "1" ]] || die "SEMANTIC_BRIDGE_WORKERS must be 1: snapshots and threads are process-local"

[[ -d "${ROOT}/backend/semantic_layer" ]] || die "backend/semantic_layer missing under ${ROOT} — rsync the repo first"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || [[ -x "$PYTHON_BIN" ]] || die "no usable python found (set SEMANTIC_PYTHON)"
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3, 10), sys.version' || die "${PYTHON_BIN} is older than 3.10"
log "python: $("$PYTHON_BIN" -V 2>&1)"

# --- 0. scope guard: profiling touches the customer's live database ------------------------------
# An empty table filter means "every table in the schema"; on an ERP that is thousands of tables and a
# GROUP BY per low-cardinality column. Refuse unless the operator says so explicitly.
if [[ -z "${SEMANTIC_TABLE_LIKE:-}" && "${SEMANTIC_ALLOW_FULL_SCAN:-0}" != "1" ]]; then
  die "SEMANTIC_TABLE_LIKE is empty — set a scope (e.g. SEMANTIC_TABLE_LIKE='LG_411_%') or SEMANTIC_ALLOW_FULL_SCAN=1"
fi

# --- 1. connection file (never printed), derived from the registered read-only datasource ---------
if [[ ! -f "$CONN_FILE" ]]; then
  [[ -f "${SECRETS}/mssql-ro.datasources.json" ]] || die "no ${CONN_FILE} and no ${SECRETS}/mssql-ro.datasources.json to derive it from"
  log "writing ${CONN_FILE} from the registered read-only datasource"
  umask 077
  "$PYTHON_BIN" - "$SECRETS" "$CONN_FILE" "$DATASOURCE_KEY" <<'PY'
import json, pathlib, sys
secrets, out, key = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
reg = json.loads((secrets / "mssql-ro.datasources.json").read_text())
src = reg["sources"][key]
pw_file = src.get("password_file") or "mssql-logo.password"
pw_path = pathlib.Path(pw_file if pw_file.startswith("/") else str(secrets / pw_file))
conn = {"datasource": "mssql", "host": src["host"], "port": str(src["port"]), "database": src["database"],
        "user": src["user"], "password": pw_path.read_text().strip(),
        "driver": src.get("driver", "FreeTDS"), "tds_version": src.get("tds_version", "7.4"),
        "kwargs": {"ClientCharset": "UTF-8"}}
out.write_text(json.dumps(conn))
print("connection fields:", [k for k in conn if k != "password"])
PY
  chmod 600 "$CONN_FILE"
fi
[[ -f "$CONN_FILE" ]] || die "missing connection file ${CONN_FILE}"

# --- 2. dedicated virtualenv ----------------------------------------------------------------------
if [[ ! -x "${VENV}/bin/python" ]]; then
  log "creating ${VENV}"
  "$PYTHON_BIN" -m venv "$VENV"
fi
log "installing bridge deps into ${VENV} (API venv untouched)"
"${VENV}/bin/python" -m pip install -q --upgrade pip
"${VENV}/bin/python" -m pip install -q -r "${ROOT}/backend/semantic_bridge/requirements.txt"
"${VENV}/bin/python" -c "import pyodbc, sqlglot, sqlalchemy, fastapi; print('  deps ok')"
odbcinst -q -d 2>/dev/null | grep -qi freetds || log "WARN: FreeTDS ODBC driver not registered (odbcinst -q -d)"

# The portal (nanobase_api, its own venv) imports semantic_layer for /bi/semantic-layer — verify, never install.
"${API_VENV}/bin/python" -c "
import importlib.util as u, sys
missing = [m for m in ('sqlalchemy', 'sqlglot', 'yaml', 'httpx') if u.find_spec(m) is None]
print('  api venv missing:', missing or 'none')
sys.exit(1 if missing else 0)
" || die "API venv lacks a light dependency the portal page needs — install it there deliberately, then re-run"

# --- 3. migration (sl_* tables in bi_meta) --------------------------------------------------------
log "alembic upgrade head (014_semantic_layer)"
"${ROOT}/scripts/server/migrate-nanobase-api.sh"

# --- 4. env file (never printed) ------------------------------------------------------------------
if [[ -z "${NANOBASE_META_DSN:-}" ]]; then
  META_PW="$(tr -d '\n\r' < "${SECRETS}/bi-meta-db.password")"
  META_PW_ENC="$(META_PW="$META_PW" "$PYTHON_BIN" -c "import os,urllib.parse; print(urllib.parse.quote_plus(os.environ['META_PW']))")"
  NANOBASE_META_DSN="postgresql+psycopg2://bi_meta:${META_PW_ENC}@127.0.0.1:5434/bi_meta"
fi
LLM_BASE="$(grep -E '^OPENAI_API_BASE=' "$API_ENV" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)"
LLM_MODEL="$(grep -E '^LLM_MODEL_NAME=' "$API_ENV" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)"
LLM_KEY="$(grep -E '^OPENAI_API_KEY=' "$API_ENV" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)"
sudo mkdir -p "$(dirname "$ENV_FILE")"
sudo chown "${SERVICE_USER:-administrator}" "$(dirname "$ENV_FILE")" 2>/dev/null || true
if [[ -f "$ENV_FILE" ]]; then
  cp "$ENV_FILE" "${ENV_FILE}.bak-$(date +%Y%m%d%H%M%S)"
  log "existing env kept at ${ENV_FILE}.bak-* (operator tuning is not silently overwritten)"
fi
umask 077
cat > "$ENV_FILE" <<ENV
SEMANTIC_STORE_DSN=${NANOBASE_META_DSN}
SEMANTIC_TENANT_ID=${SEMANTIC_TENANT_ID:-default}
SEMANTIC_DATASOURCE_ID=${SEMANTIC_DATASOURCE_ID:-logo}
SEMANTIC_KNOWLEDGE_DIR=${KNOWLEDGE}
SEMANTIC_CONNECTION_FILE=${CONN_FILE}
# Operator scope for this deployment — profiling reads the live database, keep it deliberate.
SEMANTIC_SCHEMA=${SEMANTIC_SCHEMA:-dbo}
SEMANTIC_TABLE_LIKE=${SEMANTIC_TABLE_LIKE:-}
# Table-name placeholders are discovered from the names themselves (LG_411_01_X → LG_{n0}_{n1}_X).
# SEMANTIC_CONTEXT overrides them at compile time (another firm/period without touching the catalog);
# SEMANTIC_PATTERN_LABELS only renames them for the portal.
SEMANTIC_CONTEXT=${SEMANTIC_CONTEXT:-}
SEMANTIC_PATTERN_LABELS=${SEMANTIC_PATTERN_LABELS:-}
SEMANTIC_DEFAULT_PERIOD=${SEMANTIC_DEFAULT_PERIOD:-}
SEMANTIC_DIALECT=${SEMANTIC_DIALECT:-}
SEMANTIC_MIN_SUPPORT=${SEMANTIC_MIN_SUPPORT:-3}
SEMANTIC_RECALL=${SEMANTIC_RECALL:-1}
SEMANTIC_STRICT_MISS=${SEMANTIC_STRICT_MISS:-0}
SEMANTIC_SUMMARY_MODE=${SEMANTIC_SUMMARY_MODE:-fast}
SEMANTIC_MAX_ROWS=${SEMANTIC_MAX_ROWS:-500}
# Kokpit açılışı: aynı beş toplama sorgusu her yenilemede sorulur. Sonuçlar önbellekte tutulur ve
# arka planda tazelenir; kullanıcının isteği kaynağa inmez, hazır sonucu alır. Tazeleme turu, sıcak
# sorguların toplam süresi × DUTY kadar uzayabilir — kaynak tazelemeye ayrılıp kullanıcıyı bekletmesin
# diye. REFRESH_SEC=0 tazelemeyi kapatır (her istek yeniden kaynağa iner).
SEMANTIC_CACHE_TTL_SEC=${SEMANTIC_CACHE_TTL_SEC:-300}
SEMANTIC_REFRESH_SEC=${SEMANTIC_REFRESH_SEC:-15}
SEMANTIC_REFRESH_DUTY=${SEMANTIC_REFRESH_DUTY:-5}
SEMANTIC_HOT_WINDOW_SEC=${SEMANTIC_HOT_WINDOW_SEC:-900}
SEMANTIC_STALE_MAX_SEC=${SEMANTIC_STALE_MAX_SEC:-900}
SEMANTIC_INTUGLE=${SEMANTIC_INTUGLE:-0}
OPENAI_API_BASE=${LLM_BASE:-http://172.17.0.1:8020/v1}
OPENAI_API_KEY=${LLM_KEY}
LLM_MODEL_NAME=${LLM_MODEL:-nanobaseai-bi-llm}
SEMANTIC_LLM_SLOTS=${SEMANTIC_LLM_SLOTS:-1}
SEMANTIC_QUERY_TIMEOUT_SEC=${SEMANTIC_QUERY_TIMEOUT_SEC:-120}
SEMANTIC_DEEP_TABLES=${SEMANTIC_DEEP_TABLES:-60}
SEMANTIC_PROBE_LINKS=${SEMANTIC_PROBE_LINKS:-0}
LLM_TIMEOUT_SEC=${LLM_TIMEOUT_SEC:-240}
ENV
chmod 600 "$ENV_FILE"

# --- 5. offline pipeline: profile the live database, mine knowledge, certify -----------------------
log "pipeline (profile → mine → docs → certify) — scope: ${SEMANTIC_SCHEMA:-dbo} / ${SEMANTIC_TABLE_LIKE:-<all>}"
set -a; source "$ENV_FILE"; set +a
cd "${ROOT}/backend"
PYTHONPATH="${ROOT}/backend" "${VENV}/bin/python" -m semantic_layer.cli pipeline --note "deploy $(date -Is)" | tail -40
PYTHONPATH="${ROOT}/backend" "${VENV}/bin/python" -m semantic_layer.cli status

# --- 5b. regression gate: this catalog must not answer worse than the one it replaces --------------
# A nightly catalog changes on its own: a new sense splits an old mapping, a certification is
# withdrawn, a synonym starts winning. The end-user corpus is replayed against the fresh catalog and
# compared with the last accepted run — a question that used to be answered and now is not, or one
# that used to be refused and is now answered, stops the deploy before the service picks it up.
GATE_DIR="${SEMANTIC_REPORT_DIR:-/data/nanobaseai/bi/logs}"
GATE_CORPUS="${ROOT}/tests/text2sql/enduser-50.yaml"
if [[ -f "$GATE_CORPUS" ]]; then
  sudo mkdir -p "$GATE_DIR" && sudo chown "$(id -u):$(id -g)" "$GATE_DIR" 2>/dev/null || true
  GATE_NOW="${GATE_DIR}/enduser-$(date +%Y%m%d-%H%M%S).json"
  GATE_BASE="${GATE_DIR}/enduser-baseline.json"
  if PYTHONPATH="${ROOT}/backend" "${VENV}/bin/python" "${ROOT}/tests/text2sql/enduser-eval.py"         --corpus "$GATE_CORPUS" --store "$SEMANTIC_STORE_DSN"         --datasource "${SEMANTIC_DATASOURCE_ID:-}" --tenant "${SEMANTIC_TENANT_ID:-}"         --baseline "$GATE_BASE" --gate --out "$GATE_NOW" | tail -12; then
    cp "$GATE_NOW" "$GATE_BASE"
    log "regression gate passed — baseline updated ($GATE_BASE)"
  elif [[ "${SEMANTIC_GATE_STRICT:-1}" == "1" ]]; then
    die "regression gate failed: this catalog answers worse than the one in use — report: $GATE_NOW (override with SEMANTIC_GATE_STRICT=0)"
  else
    log "WARNING regression gate failed but SEMANTIC_GATE_STRICT=0 — continuing; report: $GATE_NOW"
  fi
else
  log "regression gate skipped: corpus not deployed ($GATE_CORPUS)"
fi

# --- 6. bridge service ----------------------------------------------------------------------------
log "writing ${UNIT}"
sudo tee "$UNIT" >/dev/null <<UNITEOF
[Unit]
Description=NanobaseAI Semantic Bridge (:${PORT}) — cockpit NL→SQL
After=network-online.target
Wants=network-online.target

[Service]
User=${SERVICE_USER:-administrator}
WorkingDirectory=${ROOT}/backend
EnvironmentFile=${ENV_FILE}
Environment=PYTHONPATH=${ROOT}/backend
ExecStart=${VENV}/bin/uvicorn semantic_bridge.app:app --host 127.0.0.1 --port ${PORT} --workers ${WORKERS} --timeout-keep-alive 30
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNITEOF

# The nightly worker runs the same pipeline from the same env file and venv.
sudo tee /etc/systemd/system/nanobase-semantic-worker.service >/dev/null <<WORKEREOF
[Unit]
Description=Nanobase Semantic Layer nightly worker (profile → mine → candidates → certify → version)
After=network-online.target nanobase-semantic-bridge.service
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER:-administrator}
WorkingDirectory=${ROOT}/backend
EnvironmentFile=${ENV_FILE}
Environment=PYTHONPATH=${ROOT}/backend
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
TimeoutStartSec=7200
ExecStart=${VENV}/bin/python -m semantic_layer.cli pipeline --llm --note nightly
ExecStartPost=-/usr/bin/curl -fsS -H "X-Semantic-Admin: \${SEMANTIC_ADMIN_TOKEN}" -m 30 -X POST http://127.0.0.1:${PORT}/api/v1/semantic/reload
WORKEREOF
sudo cp "${ROOT}/infra/systemd/nanobase-semantic-worker.timer" /etc/systemd/system/
ROOT="$ROOT" VENV="$VENV" ENV_FILE="$ENV_FILE" SERVICE_USER="${SERVICE_USER:-administrator}" \
  bash "$ROOT/scripts/server/deploy-language-pool-worker.sh"
# Watchdog: a port check is not health — this one asks the bridge a real question every five minutes.
sudo cp "${ROOT}/infra/systemd/nanobase-semantic-watchdog.service" "${ROOT}/infra/systemd/nanobase-semantic-watchdog.timer" /etc/systemd/system/
sudo -E systemctl daemon-reload
sudo -E systemctl enable --now nanobase-semantic-bridge.service nanobase-semantic-worker.timer nanobase-semantic-watchdog.timer
sudo -E systemctl restart nanobase-semantic-bridge.service
sleep 3

# --- 7. smoke: the service must answer, and answer from the catalog --------------------------------
curl -fsS -H "X-Semantic-Caller: ${SEMANTIC_CALLER_TOKEN:-}" -m 20 "http://127.0.0.1:${PORT}/health" | head -c 400; echo
curl -fsS -H "X-Semantic-Caller: ${SEMANTIC_CALLER_TOKEN:-}" -m 20 "http://127.0.0.1:${PORT}/api/v1/engine" | head -c 400; echo
ASK="$(curl -fsS -H "X-Semantic-Caller: ${SEMANTIC_CALLER_TOKEN:-}" -m 240 -H 'Content-Type: application/json' -d '{"question":"2026 toplam net ciro nedir?","sampleSize":5}' "http://127.0.0.1:${PORT}/api/v1/ask")"
echo "$ASK" | head -c 700; echo
echo "$ASK" | grep -q '"type": *"TEXT_TO_SQL"' || die "ask smoke did not produce SQL — inspect journalctl -u nanobase-semantic-bridge"

# The portal page runs inside nanobase_api, which loads its own env file: give it the same catalog
# coordinates, otherwise /bi/semantic-layer can read nothing and its pipeline action always fails.
if [[ -f "$API_ENV" ]] && ! grep -q '^SEMANTIC_STORE_DSN=' "$API_ENV"; then
  log "adding SEMANTIC_* coordinates to ${API_ENV} (restart nanobase-bi-api to apply)"
  umask 077
  {
    echo ""
    echo "# Semantic Layer (portal page reads the same catalog as the bridge)"
    echo "SEMANTIC_STORE_DSN=${NANOBASE_META_DSN}"
    echo "SEMANTIC_TENANT_ID=${SEMANTIC_TENANT_ID:-default}"
    echo "SEMANTIC_DATASOURCE_ID=${SEMANTIC_DATASOURCE_ID:-logo}"
    echo "SEMANTIC_KNOWLEDGE_DIR=${KNOWLEDGE}"
    echo "SEMANTIC_SCHEMA=${SEMANTIC_SCHEMA:-dbo}"
    echo "SEMANTIC_TABLE_LIKE=${SEMANTIC_TABLE_LIKE:-}"
  } >> "$API_ENV"
fi

log "bridge is up on :${PORT}; traffic is NOT switched yet"
log "next: verification gates in docs/architecture/semantic-bridge-runbook.md, then ./scripts/server/switch-timas-api.sh semantic"
log "the portal page needs the API to reload the new router: sudo systemctl restart nanobase-bi-api  (production API restart — do it deliberately)"
