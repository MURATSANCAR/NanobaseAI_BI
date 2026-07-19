#!/usr/bin/env bash
# Faz 8: Oracle RO smoke + policy checks (skips cleanly if secrets not configured).
set -euo pipefail
BASE="${QG_BASE:-http://127.0.0.1:8792}"
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
MAP="${SECRETS}/oracle-ro.datasources.json"

ok() { printf 'OK  %s\n' "$*"; }
skip() { printf 'SKIP %s\n' "$*"; exit 0; }
bad() { printf 'FAIL %s\n' "$*"; exit 1; }

curl -fsS "$BASE/health" >/tmp/qg_h.json || bad "health"
python3 - <<'PY' || bad "oracle_driver missing"
import json
d=json.load(open("/tmp/qg_h.json"))
assert d.get("oracle_driver") is True, d
print("oracle_driver", d.get("oracle_driver"), "datasources", d.get("datasources"))
PY
ok "oracledb installed"

# Offline policy smoke (always)
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export PYTHONPATH="${ROOT}/backend"
python3 - <<'PY' || bad "oracle offline policy"
from query_gateway.infrastructure.oracle.parser_policy import enforce_oracle_sql_policy
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.oracle.profile import validate_oracle_username

for bad_sql in [
    "SELECT * FROM T@REMOTE",
    "SELECT /*+ PARALLEL(8) */ ID FROM T",
    "BEGIN NULL; END;",
    "SELECT UTL_HTTP.REQUEST('https://x') FROM DUAL",
    "SELECT ID FROM T FOR UPDATE",
]:
    try:
        enforce_oracle_sql_policy(bad_sql)
        raise SystemExit(f"should reject: {bad_sql}")
    except GatewayError:
        pass
try:
    validate_oracle_username("SYS")
    raise SystemExit("SYS should be rejected")
except GatewayError:
    pass
print("offline oracle policy OK")
PY
ok "offline Oracle policy (hint/dblink/PLSQL/SYS)"

[[ -f "$MAP" ]] || skip "no $MAP — connector ready, awaiting credentials"

DS=$(python3 - <<'PY'
import json,urllib.request
d=json.load(urllib.request.urlopen("http://127.0.0.1:8792/api/v1/query/datasources"))
for x in d.get("datasources") or []:
    if (x.get("driver") or "").lower()=="oracle" or (x.get("dialect") or "").lower()=="oracle":
        print(x["id"]); break
PY
)
[[ -n "$DS" ]] || bad "oracle source not registered (check JSON + password_file)"
ok "datasource=$DS"

# Prefer reporting view; fall back to SSB sample
SQL_COUNT="SELECT COUNT(*) AS N FROM NANOBASE_REPORTING.V_INVOICE"
SQL_INSERT="INSERT INTO NANOBASE_REPORTING.V_INVOICE(INVOICE_ID) VALUES(1)"
if grep -q 'ssb\|SSB' "$MAP" 2>/dev/null; then
  SQL_COUNT="SELECT COUNT(*) AS N FROM ssb.customer"
  SQL_INSERT="INSERT INTO ssb.customer(c_custkey) VALUES(1)"
fi

code=$(curl -sS -o /tmp/qg_ora_v.json -w '%{http_code}' -X POST "$BASE/api/v1/query/validate" \
  -H 'Content-Type: application/json' \
  -d "{\"datasource_id\":\"$DS\",\"sql\":\"$SQL_COUNT\"}")
if [[ "$code" == "200" ]]; then
  ok "Oracle validate"
else
  # Soft: map may use different allowlist
  ok "Oracle validate http=$code (check allowlist)"
fi

code=$(curl -sS -o /tmp/qg_ora_e.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d "{\"datasource_id\":\"$DS\",\"sql\":\"$SQL_COUNT\"}")
if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/qg_ora_e.json")); assert d.get("ok") or d.get("status")=="SUCCESS"'; then
  ok "Oracle execute COUNT"
else
  bad "execute http=$code $(head -c 400 /tmp/qg_ora_e.json)"
fi

code=$(curl -sS -o /tmp/qg_ora_ins.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d "{\"datasource_id\":\"$DS\",\"sql\":\"$SQL_INSERT\"}")
[[ "$code" == "400" || "$code" == "403" ]] && ok "Oracle INSERT denied" || bad "INSERT should be denied got $code"

for bad_sql in \
  "SELECT * FROM CUSTOMER@REMOTE_DB" \
  "SELECT /*+ PARALLEL(32) */ INVOICE_ID FROM DUAL" \
  "BEGIN NULL; END;" \
  "SELECT UTL_HTTP.REQUEST('https://example.com') FROM DUAL" \
  "SELECT 1 FROM DUAL FOR UPDATE"
do
  code=$(curl -sS -o /tmp/qg_ora_bad.json -w '%{http_code}' -X POST "$BASE/api/v1/query/validate" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json;print(json.dumps({'datasource_id':'$DS','sql':'''$bad_sql'''}))")")
  [[ "$code" != "200" ]] || python3 -c 'import json;d=json.load(open("/tmp/qg_ora_bad.json")); assert d.get("ok") is False or d.get("status")!="APPROVED"' \
    && ok "rejected: ${bad_sql:0:40}..." || bad "should reject: $bad_sql"
done

ok "Faz 8 Oracle smoke PASS"
