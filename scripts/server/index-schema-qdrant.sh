#!/usr/bin/env bash
# Index Postgres datasources via tools/schema-indexer → Qdrant.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INDEXER="${ROOT}/tools/schema-indexer"
PY="${ROOT}/backend/.venv/bin/python"
export SECRETS_ROOT="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
export PHASE2_OUT_DIR="${PHASE2_OUT_DIR:-${ROOT}/docs/architecture}"

if [[ -f "${ROOT}/backend/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/backend/.env"
  set +a
fi

DS_LIST="${1:-bi_reporting erp sigorta}"
RECREATE_FLAG="${SCHEMA_INDEX_RECREATE:-}"
log() { printf '[schema-index] %s\n' "$*"; }

for ds in $DS_LIST; do
  extra=()
  if [[ -n "$RECREATE_FLAG" ]]; then
    extra+=(--recreate)
  fi
  if [[ "$ds" == "bi_reporting" || "$ds" == "nanobase_test" ]]; then
    schemas="analytics,public"
  else
    schemas="public"
    extra+=(--skip-samples --skip-profile)
  fi
  log "indexing $ds (schemas=$schemas) via schema-indexer"
  PYTHONPATH="${INDEXER}" "$PY" -m cli.main \
    --datasource "$ds" \
    --schemas "$schemas" \
    --out-dir "${PHASE2_OUT_DIR}" \
    "${extra[@]+"${extra[@]}"}"
done

curl -sf http://127.0.0.1:6333/collections | python3 -c 'import sys,json; print([c["name"] for c in json.load(sys.stdin)["result"]["collections"]])'
log "done"
