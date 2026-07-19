#!/usr/bin/env bash
# Acceptance checks for Query Gateway.
set -euo pipefail
BASE="${QG_BASE:-http://127.0.0.1:8792}"
fail=0
ok() { printf 'OK  %s\n' "$*"; }
bad() { printf 'FAIL %s\n' "$*"; fail=1; }

curl -fsS "$BASE/health" >/dev/null && ok "health" || bad "health"
curl -fsS "$BASE/health/live" >/dev/null && ok "health/live" || bad "health/live"
curl -fsS "$BASE/health/ready" >/dev/null && ok "health/ready" || bad "health/ready"

# Unauthenticated internal API must fail when auth enabled (or return structured reject)
code=$(curl -sS -o /tmp/qg_int.json -w '%{http_code}' -X POST "$BASE/internal/v1/queries/validate" \
  -H 'Content-Type: application/json' \
  -d '{"executionId":"v1","datasourceId":"bi_reporting","sql":"DELETE FROM public.customers"}')
if [[ "$code" == "401" || "$code" == "400" || "$code" == "403" || "$code" == "404" || "$code" == "503" ]]; then
  ok "internal validate blocked without/against policy (http $code)"
else
  bad "internal validate unexpected $code"
fi

# SELECT allowed
code=$(curl -sS -o /tmp/qg_ok.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d '{"datasource_id":"bi_reporting","sql":"SELECT count(*) AS n FROM customers"}')
if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/qg_ok.json")); assert d["ok"] and d["rows"][0]["n"]==5'; then
  ok "SELECT count customers (=5)"
else
  bad "SELECT count (http $code) $(head -c 200 /tmp/qg_ok.json)"
fi

# LIMIT injected
code=$(curl -sS -o /tmp/qg_lim.json -w '%{http_code}' -X POST "$BASE/api/v1/query/validate" \
  -H 'Content-Type: application/json' \
  -d '{"datasource_id":"bi_reporting","sql":"SELECT * FROM products"}')
if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/qg_lim.json")); assert d["ok"] and "LIMIT" in d["sql"].upper()'; then
  ok "LIMIT injected"
else
  bad "LIMIT inject"
fi

# INSERT denied
code=$(curl -sS -o /tmp/qg_ins.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d '{"datasource_id":"bi_reporting","sql":"INSERT INTO customers(customer_name,country,segment) VALUES('\''x'\'','\''TR'\'','\''smb'\'')"}')
if [[ "$code" == "400" ]]; then
  ok "INSERT denied ($code)"
else
  bad "INSERT should be 400 got $code"
fi

# unknown table denied
code=$(curl -sS -o /tmp/qg_tbl.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d '{"datasource_id":"bi_reporting","sql":"SELECT * FROM pg_shadow"}')
if [[ "$code" == "400" ]]; then
  ok "pg_shadow denied"
else
  bad "pg_shadow should be denied ($code)"
fi

# DROP denied
code=$(curl -sS -o /tmp/qg_drop.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d '{"datasource_id":"bi_reporting","sql":"DROP TABLE customers"}')
if [[ "$code" == "400" ]]; then
  ok "DROP denied"
else
  bad "DROP should be denied ($code)"
fi

# unknown datasource / Neon RO
code=$(curl -sS -o /tmp/qg_ds.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d '{"datasource_id":"not_a_real_ds","sql":"SELECT 1"}')
if [[ "$code" == "404" ]]; then
  ok "unknown datasource blocked (404)"
else
  bad "unknown ds should be 404 (got $code)"
fi

# Neon erp/sigorta: if registered, SELECT current_database must work; else skip
if curl -fsS "$BASE/health" | python3 -c 'import sys,json; d=json.load(sys.stdin); raise SystemExit(0 if "erp" in (d.get("datasources") or []) else 1)'; then
  code=$(curl -sS -o /tmp/qg_erp.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
    -H 'Content-Type: application/json' \
    -d '{"datasource_id":"erp","sql":"SELECT current_database() AS db"}')
  if [[ "$code" == "200" ]]; then
    ok "erp Neon RO registered"
  else
    bad "erp registered but execute failed ($code)"
  fi
else
  ok "erp not registered yet (optional neon-ro map)"
fi

exit "$fail"
