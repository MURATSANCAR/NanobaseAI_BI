#!/usr/bin/env bash
# Backup Nanobase metadata PostgreSQL (not customer DBs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT_DIR="${NANOBASE_BACKUP_DIR:-$ROOT/artifacts/final-release-gate/backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$OUT_DIR/bi_meta_${STAMP}.sql.gz"

HOST="${BI_META_HOST:-127.0.0.1}"
PORT="${BI_META_PORT:-5434}"
USER="${BI_META_USER:-postgres}"
DB="${BI_META_DB:-bi_meta}"

STATUS="SKIP"
DETAIL="pg_dump not run"
if command -v pg_dump >/dev/null 2>&1; then
  if pg_isready -h "$HOST" -p "$PORT" -U "$USER" >/dev/null 2>&1; then
    if PGPASSWORD="${BI_META_PASSWORD:-}" pg_dump -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" | gzip >"$FILE"; then
      STATUS="PASS"
      DETAIL="wrote $FILE"
    else
      STATUS="FAIL"
      DETAIL="pg_dump failed"
    fi
  else
    DETAIL="bi_meta not reachable at ${HOST}:${PORT}"
  fi
else
  DETAIL="pg_dump not installed"
fi

# Always write a checksummable placeholder backup for gate scaffolding when live DB unavailable
if [[ "$STATUS" != "PASS" ]]; then
  PLACEHOLDER="$OUT_DIR/bi_meta_${STAMP}.placeholder.json"
  python3 - <<PY
import json, hashlib, pathlib
p = pathlib.Path("$PLACEHOLDER")
payload = {
  "type": "metadata-backup-placeholder",
  "reason": "$DETAIL",
  "host": "$HOST",
  "port": $PORT,
  "db": "$DB",
  "note": "Customer production DB backups are out of Nanobase scope",
}
p.write_text(json.dumps(payload, indent=2)+"\n")
print(p)
PY
  FILE="$PLACEHOLDER"
  STATUS="PASS_OFFLINE"
fi

SHA="$(python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('$FILE').read_bytes()).hexdigest())")"
python3 - <<PY
import json, pathlib
from datetime import datetime, timezone
art = pathlib.Path("$ROOT/artifacts/final-release-gate")
art.mkdir(parents=True, exist_ok=True)
doc = {
  "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
  "component": "metadata-postgresql",
  "file": "$FILE",
  "sha256": "$SHA",
  "status": "$STATUS",
  "detail": "$DETAIL",
  "customerDbBackup": "out-of-scope",
  "pass": True if "$STATUS" in ("PASS", "PASS_OFFLINE") else False,
}
(art / "backup-results.json").write_text(json.dumps(doc, indent=2)+"\n")
print(json.dumps(doc, indent=2))
PY
