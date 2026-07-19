#!/usr/bin/env bash
# Faz 6.8: production chat path must not call DB-GPT chat_with_db_execute.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fail=0
if rg -n "chat_with_db_execute" "$ROOT/backend/nanobase_api" "$ROOT/src" 2>/dev/null | rg -v "NOT used|never used|is NOT used|#"; then
  echo "FAIL: chat_with_db_execute referenced in nanobase_api/FE production paths"
  fail=1
else
  echo "OK  nanobase_api/FE have no active chat_with_db_execute calls"
fi
if rg -n "chat_with_db_execute" "$ROOT/backend/bridge" >/dev/null 2>&1; then
  echo "WARN bridge still contains chat_with_db_execute (legacy; not used by /bi chat)"
fi
exit "$fail"
