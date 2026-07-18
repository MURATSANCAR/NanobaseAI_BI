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
dbgpt stop webserver --port "$PORT" || true
