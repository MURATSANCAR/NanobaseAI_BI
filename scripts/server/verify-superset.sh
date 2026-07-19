#!/usr/bin/env bash
# Verify Superset analytics bridge (API contract + optional live engine).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
API_BASE="${API_BASE:-http://127.0.0.1:8790}"
SUPERSET_URL="${BI_SUPERSET_URL:-http://127.0.0.1:8089}"

echo "== analytics status (API) =="
STATUS="$(curl -fsS "$API_BASE/api/v1/bi/analytics/status" || true)"
echo "$STATUS" | head -c 500
echo

if ! echo "$STATUS" | grep -q '"enabled"'; then
  echo "FAIL: status missing enabled field (is nanobase_api running with analytics_api?)"
  exit 1
fi

echo "== analytics dashboards shape =="
DASH="$(curl -fsS "$API_BASE/api/v1/bi/analytics/dashboards" || true)"
echo "$DASH" | head -c 300
echo
if ! echo "$DASH" | grep -q '"dashboards"'; then
  echo "FAIL: dashboards must be { dashboards: [...] }"
  exit 1
fi

ENABLED="$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('enabled', False))" 2>/dev/null || echo false)"
if [[ "$ENABLED" == "True" || "$ENABLED" == "true" ]]; then
  echo "== live Superset health =="
  curl -fsS -o /dev/null -w "superset_http=%{http_code}\n" "$SUPERSET_URL/health" || \
    curl -fsS -o /dev/null -w "superset_login_page=%{http_code}\n" "$SUPERSET_URL/login/" || true
  echo "OK: analytics enabled — guest-token / pin require a dashboard + DB in Superset UI"
else
  echo "OK: analytics disabled (shaped stubs). Enable with BI_SUPERSET_ENABLED=1 + secrets."
fi

echo "== guest-token smoke (dashboard 1 if present) =="
DASH_ID="$(echo "$DASH" | python3 -c "import sys,json; d=json.load(sys.stdin).get('dashboards') or []; print(d[0]['id'] if d else '')" 2>/dev/null || true)"
if [[ -n "$DASH_ID" && ( "$ENABLED" == "True" || "$ENABLED" == "true" ) ]]; then
  GT="$(curl -fsS -X POST "$API_BASE/api/v1/bi/analytics/guest-token/${DASH_ID}")"
  echo "$GT" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('token') and d.get('embed_uuid'); print('guest_ok', d['embed_uuid'][:8])"
fi

echo "== unit tests (optional) =="
cd "$ROOT/backend"
if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY=python3; fi
if "$PY" -c "import pytest" 2>/dev/null; then
  "$PY" -m pytest nanobase_api/tests/unit/test_analytics_api.py -q --tb=line
else
  echo "skip pytest (not installed in runtime venv)"
fi
echo "verify-superset: PASS"
