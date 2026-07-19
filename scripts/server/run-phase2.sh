#!/usr/bin/env bash
# Faz 2: schema index (all DS) + quality gate (server).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="${ROOT}/backend"
PY="${BACKEND}/.venv/bin/python"
export NANOBASE_ROOT="${ROOT}"
export PHASE2_OUT_DIR="${ROOT}/docs/architecture"
export SECRETS_ROOT="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
export BI_SCHEMA_COLLECTION="${BI_SCHEMA_COLLECTION:-bi_schema_bi_reporting}"
export NANOBASE_API_BASE="${NANOBASE_API_BASE:-http://127.0.0.1:8790}"

if [[ -f "${BACKEND}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${BACKEND}/.env"
  set +a
fi

echo "[phase2] indexing schema → Qdrant (bi_reporting erp sigorta)"
"${ROOT}/scripts/server/index-schema-qdrant.sh" "bi_reporting erp sigorta"

echo "[phase2] running 20-question quality suite (nanobase nl2sql-plan)"
"$PY" -u "${BACKEND}/scripts/phase2_quality.py"

echo "[phase2] done → ${PHASE2_OUT_DIR}/phase-2-results.md"
