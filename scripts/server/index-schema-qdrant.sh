#!/usr/bin/env bash
# Index Postgres datasources into Qdrant (bi_reporting / erp / sigorta).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${ROOT}/backend/.venv/bin/python"
export SECRETS_ROOT="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
export PHASE2_OUT_DIR="${ROOT}/docs/architecture"

# Prefer backend/.env for embed key (avoid sudo)
if [[ -f "${ROOT}/backend/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/backend/.env"
  set +a
fi

DS_LIST="${1:-bi_reporting erp sigorta}"
log() { printf '[schema-index] %s\n' "$*"; }

for ds in $DS_LIST; do
  export BI_SCHEMA_DATASOURCE="$ds"
  export BI_SCHEMA_COLLECTION="bi_schema_${ds}"
  if [[ "$ds" == "bi_reporting" ]]; then
    export BI_SCHEMA_SCHEMAS="${BI_SCHEMA_SCHEMAS:-analytics,public}"
    export BI_SCHEMA_SKIP_SAMPLES="${BI_SCHEMA_SKIP_SAMPLES:-0}"
    export BI_SCHEMA_SKIP_COUNTS="${BI_SCHEMA_SKIP_COUNTS:-0}"
  else
    export BI_SCHEMA_SCHEMAS="${BI_SCHEMA_SCHEMAS:-public}"
    export BI_SCHEMA_SKIP_SAMPLES=1
    export BI_SCHEMA_SKIP_COUNTS=1
  fi
  log "indexing $ds → $BI_SCHEMA_COLLECTION"
  "$PY" "${ROOT}/backend/scripts/schema_index_qdrant.py"
done

curl -sf http://127.0.0.1:6333/collections | python3 -c 'import sys,json; print([c["name"] for c in json.load(sys.stdin)["result"]["collections"]])'
log "done"
