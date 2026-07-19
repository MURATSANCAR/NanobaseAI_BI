#!/usr/bin/env bash
# Faz 2: schema index + quality gate (server).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="${ROOT}/backend"
PY="${BACKEND}/.venv/bin/python"
export PHASE2_OUT_DIR="${ROOT}/docs/architecture"
export SECRETS_ROOT="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"

echo "[phase2] indexing schema → Qdrant"
"$PY" "${BACKEND}/scripts/schema_index_qdrant.py"

echo "[phase2] running 20-question quality suite"
"$PY" "${BACKEND}/scripts/phase2_quality.py"

echo "[phase2] done → ${PHASE2_OUT_DIR}/phase-2-results.md"
