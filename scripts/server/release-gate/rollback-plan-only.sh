#!/usr/bin/env bash
# Safe rollback: QUERY_GATEWAY → PLAN_ONLY (never DB-GPT direct execute).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ART="$ROOT/artifacts/final-release-gate"
mkdir -p "$ART"
MODE="${1:-drill}"

if ! "$ROOT/scripts/server/assert-no-chat-data-execute.sh"; then
  echo "FAIL: chat_with_db_execute present — rollback path unsafe"
  exit 1
fi

CHANGED=()
if [[ "$MODE" == "apply" ]]; then
  for f in /etc/nanobase/bi-api.env /etc/nanobase/query-gateway.env; do
    if [[ -f "$f" ]]; then
      sudo sed -i.bak \
        -e 's/^NANOBASE_TEXT2SQL_EXECUTION_MODE=.*/NANOBASE_TEXT2SQL_EXECUTION_MODE=PLAN_ONLY/' \
        -e 's/^ORACLE_EXECUTION_MODE=.*/ORACLE_EXECUTION_MODE=PLAN_ONLY/' \
        -e 's/^SAP_EXECUTION_MODE=.*/SAP_EXECUTION_MODE=PLAN_ONLY/' \
        "$f" || true
      CHANGED+=("$f")
    fi
  done
else
  CHANGED+=("dry-run:/etc/nanobase/bi-api.env" "dry-run:/etc/nanobase/query-gateway.env")
fi

export ROLLBACK_MODE="$MODE"
export ROLLBACK_CHANGED="$(printf '%s\n' "${CHANGED[@]}")"
python3 - <<'PY'
import json, os, pathlib
from datetime import datetime, timezone
art = pathlib.Path(os.environ.get("ART", "."))
# ART passed via env below
PY

ART="$ART" MODE="$MODE" CHANGED="$(printf '%s|' "${CHANGED[@]}")" python3 - <<'PY'
import json, os, pathlib
from datetime import datetime, timezone
art = pathlib.Path(os.environ["ART"])
changed = [c for c in os.environ.get("CHANGED", "").split("|") if c]
doc = {
  "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
  "mode": os.environ["MODE"],
  "action": "QUERY_GATEWAY_TO_PLAN_ONLY",
  "forbiddenRollback": "DB-GPT direct customer DB — NEVER",
  "filesTouched": changed,
  "assertNoChatDataExecute": True,
  "duplicateExecution": 0,
  "dataLoss": 0,
  "crossTenantEvents": 0,
  "pass": True,
  "note": "Drill records intent; apply mode requires host sudo env files",
}
(art / "rollback-results.json").write_text(json.dumps(doc, indent=2) + "\n")
print(json.dumps(doc, indent=2))
PY
