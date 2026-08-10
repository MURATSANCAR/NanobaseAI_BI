#!/usr/bin/env bash
# Start DB-GPT (:5670) then the BI bridge (default :8787; prod portal uses :8789).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "error: run ./scripts/setup.sh first" >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export DBGPT_HOME="${DBGPT_HOME:-$ROOT/.dbgpt}"
mkdir -p "$DBGPT_HOME"

export BRIDGE_PORT="${BRIDGE_PORT:-8787}"
export DBGPT_PORT="${DBGPT_PORT:-5670}"

# Local LLM :8010 required. Remote proxy :8015 (MobilTest LLM-SERVER.md) is
# opt-in only via ALLOW_REMOTE_LLM_FALLBACK=1 — never fall back silently.
if [[ -n "${OPENAI_API_BASE:-}" ]]; then
  export OPENAI_API_BASE
  echo "info: using preset OPENAI_API_BASE=${OPENAI_API_BASE}"
elif curl -sf --connect-timeout 1 "http://127.0.0.1:8010/v1/models" >/dev/null 2>&1; then
  export OPENAI_API_BASE="http://127.0.0.1:8010/v1"
elif [[ "${ALLOW_REMOTE_LLM_FALLBACK:-0}" == "1" ]] \
  && curl -sf --connect-timeout 2 "http://38.247.162.28:8015/v1/models" >/dev/null 2>&1; then
  {
    echo "############################################################"
    echo "# WARNING: local LLM :8010 is DOWN."
    echo "# ALLOW_REMOTE_LLM_FALLBACK=1 set — routing LLM traffic to"
    echo "# the REMOTE PUBLIC proxy http://38.247.162.28:8015/v1."
    echo "# Prompts/results leave this host. Unset the flag to forbid."
    echo "############################################################"
  } >&2
  export OPENAI_API_BASE="http://38.247.162.28:8015/v1"
else
  {
    echo "error: local LLM not reachable on http://127.0.0.1:8010/v1."
    echo "  Start the local LLM, or set OPENAI_API_BASE explicitly,"
    echo "  or set ALLOW_REMOTE_LLM_FALLBACK=1 to allow the remote proxy :8015."
  } >&2
  exit 1
fi
export OPENAI_API_KEY="${OPENAI_API_KEY:-nanobase-local}"
export LLM_MODEL_NAME="${LLM_MODEL_NAME:-nanobase-qwen36-35b-a3b-mtp}"
export EMBEDDING_MODEL_API_URL="${EMBEDDING_MODEL_API_URL:-${OPENAI_API_BASE}/embeddings}"

# Bridge extras
if command -v uv >/dev/null 2>&1 || [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV_BIN="$(command -v uv 2>/dev/null || echo "${HOME}/.local/bin/uv")"
  "$UV_BIN" pip install -q -r bridge/requirements.txt
else
  python -m pip install -q -r bridge/requirements.txt
fi

# Stop stale DB-GPT + bridge only (never touch QA runner :8787 unless bridge uses it)
"$ROOT/scripts/stop.sh" >/dev/null 2>&1 || true
if command -v lsof >/dev/null; then
  for p in "$DBGPT_PORT" "$BRIDGE_PORT"; do
    pids="$(lsof -ti "tcp:${p}" -sTCP:LISTEN 2>/dev/null || true)"
    [[ -n "$pids" ]] && kill -TERM $pids 2>/dev/null || true
  done
  sleep 1
fi

CONFIG="$ROOT/configs/dbgpt-openai-compat.toml"
echo "LLM OPENAI_API_BASE=$OPENAI_API_BASE"
echo "Starting DB-GPT on :${DBGPT_PORT}..."
(
  cd "$ROOT"
  exec dbgpt start web --config "$CONFIG" --yes
) >"$DBGPT_HOME/dbgpt.log" 2>&1 &
echo $! >"$DBGPT_HOME/dbgpt.pid"
disown || true

for i in $(seq 1 90); do
  if curl -sf --connect-timeout 1 "http://127.0.0.1:${DBGPT_PORT}/" >/dev/null 2>&1; then
    echo "DB-GPT ready"
    break
  fi
  if [[ "$i" -eq 90 ]]; then
    echo "error: DB-GPT did not become ready — see $DBGPT_HOME/dbgpt.log" >&2
    exit 1
  fi
  sleep 1
done

SOURCES_JSON="${BI_SOURCES_FILE:-$ROOT/../configs/sources/local/connection.local.json}"
# Server deploy path
if [[ ! -f "$SOURCES_JSON" && -f /data/nanobaseai/bi/secrets/connection.local.json ]]; then
  SOURCES_JSON=/data/nanobaseai/bi/secrets/connection.local.json
fi
if [[ -f "$SOURCES_JSON" ]]; then
  BI_SOURCES_FILE="$SOURCES_JSON" \
    DBGPT_BASE="http://127.0.0.1:${DBGPT_PORT}" \
    "$ROOT/scripts/register-neon-sources.sh" || echo "warn: neon register failed (check passwords / DB-GPT API)"
fi

export DBGPT_BASE="http://127.0.0.1:${DBGPT_PORT}"
export BI_SOURCES_FILE="${BI_SOURCES_FILE:-$SOURCES_JSON}"
echo "Starting BI bridge on :${BRIDGE_PORT} → $DBGPT_BASE"
(
  cd "$ROOT"
  exec python -m uvicorn bridge.app:app --host 0.0.0.0 --port "${BRIDGE_PORT}" --workers 2
) >"$DBGPT_HOME/bridge.log" 2>&1 &
echo $! >"$DBGPT_HOME/bridge.pid"
disown || true

sleep 2
if curl -sf "http://127.0.0.1:${BRIDGE_PORT}/health"; then
  echo
  echo "OK — BI bridge http://127.0.0.1:${BRIDGE_PORT}"
else
  echo "error: bridge health failed — see $DBGPT_HOME/bridge.log" >&2
  exit 1
fi
echo "Logs: $DBGPT_HOME/dbgpt.log , $DBGPT_HOME/bridge.log"
