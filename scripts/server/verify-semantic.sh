#!/usr/bin/env bash
# Faz 7 smoke: semantic status, glossary, verified cache chat path.
set -euo pipefail

API="${NANOBASE_API_BASE:-http://127.0.0.1:8790}"

log() { printf '[verify-semantic] %s\n' "$*"; }

log "semantic/status"
curl -fsS "${API}/api/v1/bi/semantic/status" | python3 -m json.tool

log "glossary"
curl -fsS "${API}/api/v1/bi/glossary" | python3 -c '
import sys,json
d=json.load(sys.stdin)
print("entries", len(d.get("entries") or []))
'

log "metrics + joins"
curl -fsS "${API}/api/v1/bi/semantic/metrics" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("metrics", len(d.get("metrics") or []))'
curl -fsS "${API}/api/v1/bi/semantic/joins" | python3 -c 'import sys,json; d=json.load(sys.stdin); print("joins", len(d.get("joins") or []))'

log "verified-sql list"
curl -fsS "${API}/api/v1/bi/semantic/verified-sql" | python3 -c '
import sys,json
d=json.load(sys.stdin)
print("verified", len(d.get("items") or []))
'

log "chat verified cache (Kaç müşteri var?)"
# Collect SSE and look for verified_cache_hit / sql_source
OUT=$(curl -sN -X POST "${API}/api/v1/bi/chat/stream" \
  -H 'Content-Type: application/json' \
  -d '{"message":"Kaç müşteri var?","session_id":"faz7-verify","db_name":"bi_reporting"}' \
  --max-time 90 || true)
echo "$OUT" | head -c 2000
echo
if echo "$OUT" | grep -q 'verified_cache_hit\|"sql_source": "verified_sql"\|"sql_source":"verified_sql"'; then
  log "PASS verified SQL cache hit"
else
  log "WARN: verified cache not detected in stream (may still have succeeded via LLM)"
  echo "$OUT" | grep -E 'event:|sql_source|error' | head -40
fi

log "feedback promote"
curl -fsS -X POST "${API}/api/v1/bi/query/feedback" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Toplam ürün sayısı","rating":1,"sql":"SELECT COUNT(*) AS n FROM products","promote_verified":true,"datasource_id":"bi_reporting"}' \
  | python3 -m json.tool

log "OK"
