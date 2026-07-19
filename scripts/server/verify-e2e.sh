#!/usr/bin/env bash
# End-to-end Nanobase BI stack checks (loopback).
set -euo pipefail
API="${NANOBASE_API_BASE:-http://127.0.0.1:8790}"
QG="${QG_BASE:-http://127.0.0.1:8792}"
fail=0
ok() { printf 'OK  %s\n' "$*"; }
bad() { printf 'FAIL %s\n' "$*"; fail=1; }

curl -fsS "$API/health" | python3 -c 'import sys,json;d=json.load(sys.stdin); assert d.get("engine")=="nanobase_api" and d.get("meta") is True' \
  && ok "API health nanobase_api+meta" || bad "API health"

curl -fsS "$API/api/v1/bi/status" | python3 -c 'import sys,json;d=json.load(sys.stdin); assert d.get("status")=="ready" and d.get("query_gateway") is True' \
  && ok "BI status ready" || bad "BI status"

curl -fsS "$QG/health" | python3 -c 'import sys,json;d=json.load(sys.stdin); assert "bi_reporting" in d.get("datasources",[])' \
  && ok "QG bi_reporting" || bad "QG health"

# schema must be non-empty for active bi_reporting
curl -fsS "$API/api/v1/bi/schema" | python3 -c 'import sys,json;d=json.load(sys.stdin); assert (d.get("table_count") or len(d.get("tables") or []))>=3, d' \
  && ok "schema tables present" || bad "schema empty"

curl -fsS "$API/api/v1/bi/semantic/status" | python3 -c 'import sys,json;d=json.load(sys.stdin); assert d.get("enabled") and d.get("verified_sql",0)>=1' \
  && ok "semantic enabled" || bad "semantic"

# Neon optional
if curl -fsS "$QG/health" | python3 -c 'import sys,json;d=json.load(sys.stdin); raise SystemExit(0 if "erp" in d.get("datasources",[]) else 1)'; then
  code=$(curl -sS -o /tmp/e2e_erp.json -w '%{http_code}' -X POST "$QG/api/v1/query/execute" \
    -H 'Content-Type: application/json' \
    -d '{"datasource_id":"erp","sql":"SELECT current_user AS u"}')
  if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/e2e_erp.json")); assert d["ok"] and str(d["rows"][0]["u"]).startswith("bi_")'; then
    ok "erp uses bi_*_ro role"
  else
    bad "erp RO role check ($code) $(head -c 200 /tmp/e2e_erp.json)"
  fi
else
  ok "erp not registered (skip)"
fi

# verified chat
OUT=$(curl -sN -X POST "$API/api/v1/bi/chat/stream" -H 'Content-Type: application/json' \
  -d '{"message":"Kaç müşteri var?","session_id":"e2e","db_name":"bi_reporting"}' --max-time 90 || true)
echo "$OUT" | grep -q 'verified_sql\|verified_cache_hit\|nl2sql_plan\|nanobase-nl2sql-plan' && ok "chat workflow/cache" || bad "chat workflow"

# workflow plan endpoint (no execute)
curl -fsS -X POST "$API/api/v1/bi/workflows/nl2sql-plan" -H 'Content-Type: application/json' \
  -d '{"question":"Ödenmemiş fatura tutarı toplamı nedir?"}' \
  | python3 -c 'import sys,json;d=json.load(sys.stdin); assert d.get("executes") is False and d.get("sql"); print("plan tables", d.get("tables"))' \
  && ok "nl2sql-plan workflow" || bad "nl2sql-plan"

curl -fsS "$API/api/v1/bi/secrets/status" | python3 -c 'import sys,json;d=json.load(sys.stdin); assert d.get("mode") in ("file","vault+file")' \
  && ok "secrets status" || bad "secrets status"

# rich schema smoke if present
code=$(curl -sS -o /tmp/e2e_inv.json -w '%{http_code}' -X POST "$QG/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d '{"datasource_id":"bi_reporting","sql":"SELECT count(*) AS n FROM invoices"}')
if [[ "$code" == "200" ]]; then
  ok "rich schema invoices"
else
  ok "rich schema not applied yet (optional)"
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
[[ -x "$ROOT/scripts/server/verify-query-gateway.sh" ]] && "$ROOT/scripts/server/verify-query-gateway.sh" || bad "verify-query-gateway"

exit "$fail"
