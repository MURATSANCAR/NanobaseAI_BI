#!/usr/bin/env bash
# Start DB-GPT (:5670) then the BI bridge (:8787).
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

# Prefer local :8010, else remote public proxy :8015 (MobilTest LLM-SERVER.md)
if curl -sf --connect-timeout 1 "http://127.0.0.1:8010/v1/models" >/dev/null 2>&1; then
  export OPENAI_API_BASE="${OPENAI_API_BASE:-http://127.0.0.1:8010/v1}"
elif curl -sf --connect-timeout 2 "http://38.247.162.28:8015/v1/models" >/dev/null 2>&1; then
  export OPENAI_API_BASE="${OPENAI_API_BASE:-http://38.247.162.28:8015/v1}"
else
  export OPENAI_API_BASE="${OPENAI_API_BASE:-http://127.0.0.1:8010/v1}"
  echo "warn: LLM not reachable on :8010 or :8015 — starting anyway (chat will fail until LLM is up)" >&2
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

# Stop stale listeners
"$ROOT/scripts/stop.sh" >/dev/null 2>&1 || true
if command -v lsof >/dev/null; then
  for p in 5670 8787; do
    pids="$(lsof -ti "tcp:${p}" -sTCP:LISTEN 2>/dev/null || true)"
    [[ -n "$pids" ]] && kill -TERM $pids 2>/dev/null || true
  done
  sleep 1
fi

CONFIG="$ROOT/configs/dbgpt-openai-compat.toml"
echo "LLM OPENAI_API_BASE=$OPENAI_API_BASE"
echo "Starting DB-GPT on :${DBGPT_PORT:-5670}..."
nohup dbgpt start web --config "$CONFIG" --yes >"$DBGPT_HOME/dbgpt.log" 2>&1 &
echo $! >"$DBGPT_HOME/dbgpt.pid"

# Wait for DB-GPT
for i in $(seq 1 60); do
  if curl -sf --connect-timeout 1 "http://127.0.0.1:${DBGPT_PORT:-5670}/" >/dev/null 2>&1; then
    echo "DB-GPT ready"
    break
  fi
  sleep 1
done

# Register Neon sources if local file exists
if [[ -f "$ROOT/../configs/sources/local/connection.local.json" ]]; then
  BI_SOURCES_FILE="$ROOT/../configs/sources/local/connection.local.json" \
    DBGPT_BASE="http://127.0.0.1:${DBGPT_PORT:-5670}" \
    "$ROOT/scripts/register-neon-sources.sh" || echo "warn: neon register failed (check passwords / DB-GPT API)"
fi

export DBGPT_BASE="http://127.0.0.1:${DBGPT_PORT:-5670}"
export BRIDGE_PORT=8787
export BI_SOURCES_FILE="${BI_SOURCES_FILE:-$ROOT/../configs/sources/local/connection.local.json}"
echo "Starting BI bridge on :8787 → $DBGPT_BASE"
cd "$ROOT"
nohup python -m uvicorn bridge.app:app --host 0.0.0.0 --port 8787 >"$DBGPT_HOME/bridge.log" 2>&1 &
echo $! >"$DBGPT_HOME/bridge.pid"

sleep 1
curl -sf "http://127.0.0.1:8787/health" && echo && echo "OK — FE proxy target http://127.0.0.1:8787"
echo "Logs: $DBGPT_HOME/dbgpt.log , $DBGPT_HOME/bridge.log"
