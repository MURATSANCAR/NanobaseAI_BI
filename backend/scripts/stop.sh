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
echo "Stopping DB-GPT webserver on port ${PORT}..."

if command -v dbgpt >/dev/null 2>&1; then
  dbgpt stop webserver --port "$PORT" 2>/dev/null || true
fi

# Fallback: CLI may not find daemonized/foreground processes
if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -ti "tcp:${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    echo "Killing listeners on :${PORT}: ${pids}"
    # shellcheck disable=SC2086
    kill -TERM ${pids} 2>/dev/null || true
    sleep 1
    still="$(lsof -ti "tcp:${PORT}" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -n "${still}" ]]; then
      # shellcheck disable=SC2086
      kill -KILL ${still} 2>/dev/null || true
    fi
  fi
fi

echo "Done."
