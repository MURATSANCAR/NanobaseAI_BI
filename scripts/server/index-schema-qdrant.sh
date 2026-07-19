#!/usr/bin/env bash
# Index Postgres datasources via tools/schema-indexer → Qdrant.
# Default: reporting id (if password present) + every id in neon-ro.datasources.json.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INDEXER="${ROOT}/tools/schema-indexer"
PY="${ROOT}/backend/.venv/bin/python"
export SECRETS_ROOT="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
export PHASE2_OUT_DIR="${PHASE2_OUT_DIR:-${ROOT}/docs/architecture}"
REPORTING_ID="${REPORTING_DATASOURCE_ID:-bi_reporting}"

if [[ -f "${ROOT}/backend/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/backend/.env"
  set +a
fi

discover_datasources() {
  python3 - <<'PY'
import json, os
from pathlib import Path
secrets = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
ids = []
rid = (os.environ.get("REPORTING_DATASOURCE_ID") or "bi_reporting").strip()
if (secrets / "reporting-ro.password").is_file():
    ids.append(rid)
neon = secrets / "neon-ro.datasources.json"
if neon.is_file():
    raw = json.loads(neon.read_text(encoding="utf-8"))
    for sid in (raw.get("sources") or {}):
        if sid and sid not in ids:
            ids.append(str(sid))
print(" ".join(ids))
PY
}

if [[ $# -ge 1 && -n "${1:-}" ]]; then
  DS_LIST="$*"
else
  DS_LIST="$(discover_datasources)"
fi
[[ -n "$DS_LIST" ]] || { echo "[schema-index] ERROR: no datasources discovered" >&2; exit 1; }

RECREATE_FLAG="${SCHEMA_INDEX_RECREATE:-}"
log() { printf '[schema-index] %s\n' "$*"; }

for ds in $DS_LIST; do
  extra=()
  if [[ -n "$RECREATE_FLAG" ]]; then
    extra+=(--recreate)
  fi
  if [[ "$ds" == "$REPORTING_ID" || "$ds" == "nanobase_test" ]]; then
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
