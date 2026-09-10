#!/usr/bin/env bash
# Only the Python release runner may publish catalog changes.
set -euo pipefail
ROOT="${SEMANTIC_NIGHTLY_ROOT:-/data/nanobaseai/bi/frontend}"
PYTHON="${SEMANTIC_NIGHTLY_PYTHON:-/data/nanobaseai/bi/semantic-venv/bin/python}"
ENVF="${SEMANTIC_BRIDGE_ENV:-/etc/nanobase/semantic-bridge.env}"
if [[ -z "${SEMANTIC_STORE_DSN:-}" && -r "$ENVF" ]]; then
  set -a; source "$ENVF"; set +a
fi
: "${SEMANTIC_STORE_DSN:?semantic store is required}"
export PYTHONPATH="$ROOT/backend"
export SEMANTIC_NIGHTLY_ROOT="$ROOT"
cd "$ROOT"
exec "$PYTHON" -m semantic_layer.nightly
