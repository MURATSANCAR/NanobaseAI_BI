#!/usr/bin/env bash
# Faz 2: schema-indexer + 20-question smoke suite.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${ROOT}/backend/.venv/bin/python"
export NANOBASE_ROOT="${ROOT}"
export PHASE2_OUT_DIR="${ROOT}/docs/architecture"
export SECRETS_ROOT="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
export BI_SCHEMA_COLLECTION="${BI_SCHEMA_COLLECTION:-bi_schema_bi_reporting}"
export NANOBASE_API_BASE="${NANOBASE_API_BASE:-http://127.0.0.1:8790}"

if [[ -f "${ROOT}/backend/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/backend/.env"
  set +a
fi

# First migration from legacy indexer points: recreate reporting collection
export SCHEMA_INDEX_RECREATE="${SCHEMA_INDEX_RECREATE:-1}"

echo "[phase2] schema-indexer → Qdrant"
"${ROOT}/scripts/server/index-schema-qdrant.sh" "${1:-bi_reporting}"

# ensure pyyaml for smoke runner
"$PY" -c "import yaml" 2>/dev/null || "$PY" -m pip install -q pyyaml

echo "[phase2] 20-question smoke suite"
"$PY" -u "${ROOT}/tests/text2sql/run-smoke-tests.py" --write-expected

echo "[phase2] done → ${PHASE2_OUT_DIR}/phase-2-results.md"
