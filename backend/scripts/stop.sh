#!/usr/bin/env bash
# Stop DB-GPT webserver.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${DBGPT_PORT:-5670}"
BRIDGE_PORT="${BRIDGE_PORT:-8787}"
echo "Stopping DB-GPT webserver on port ${PORT} and bridge on ${BRIDGE_PORT}..."

if command -v dbgpt >/dev/null 2>&1; then
  dbgpt stop webserver --port "$PORT" 2>/dev/null || true
fi

if command -v lsof >/dev/null 2>&1; then
  for p in "$PORT" "$BRIDGE_PORT"; do
    pids="$(lsof -ti "tcp:${p}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${pids}" ]]; then
      echo "Killing listeners on :${p}: ${pids}"
      # shellcheck disable=SC2086
      kill -TERM ${pids} 2>/dev/null || true
    fi
  done
  sleep 1
  for p in "$PORT" "$BRIDGE_PORT"; do
    still="$(lsof -ti "tcp:${p}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${still}" ]]; then
      # shellcheck disable=SC2086
      kill -KILL ${still} 2>/dev/null || true
    fi
  done
fi

rm -f "${DBGPT_HOME:-$ROOT/.dbgpt}/dbgpt.pid" "${DBGPT_HOME:-$ROOT/.dbgpt}/bridge.pid" 2>/dev/null || true
echo "Done."
