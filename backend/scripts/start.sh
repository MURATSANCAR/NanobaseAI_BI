#!/usr/bin/env bash
# Start DB-GPT webserver (backend API; built-in UI on :5670 is unused by Nanobase FE).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "error: .venv missing — run ./scripts/setup.sh first" >&2
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

CONFIG="$ROOT/configs/dbgpt-openai-compat.toml"
PORT="${DBGPT_PORT:-5670}"

echo "DBGPT_HOME=$DBGPT_HOME"
echo "OPENAI_API_BASE=${OPENAI_API_BASE:-http://127.0.0.1:8010/v1}"
echo "LLM_MODEL_NAME=${LLM_MODEL_NAME:-nanobase-qwen36-35b-a3b-mtp}"
echo "Starting DB-GPT on http://127.0.0.1:${PORT} (config: $CONFIG)"

exec dbgpt start web --config "$CONFIG" --yes
