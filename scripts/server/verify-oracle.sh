#!/usr/bin/env bash
# Faz 8: Oracle RO smoke (skips cleanly if secrets not configured).
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

# Offline dialect check via validate against a synthetic registration is not possible
# without the map — if map missing, skip live tests.
[[ -f "$MAP" ]] || skip "no $MAP — connector ready, awaiting credentials"

# Pick first oracle source id from health/list
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

code=$(curl -sS -o /tmp/qg_ora_v.json -w '%{http_code}' -X POST "$BASE/api/v1/query/validate" \
  -H 'Content-Type: application/json' \
  -d "{\"datasource_id\":\"$DS\",\"sql\":\"SELECT COUNT(*) AS n FROM ssb.customer\"}")
if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/qg_ora_v.json")); assert d["ok"]; assert "FETCH" in d["sql"].upper() or "ROWNUM" in d["sql"].upper() or "LIMIT" in d["sql"].upper()'; then
  ok "Oracle validate + row limit rewrite"
else
  bad "validate http=$code $(head -c 300 /tmp/qg_ora_v.json)"
fi

code=$(curl -sS -o /tmp/qg_ora_e.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d "{\"datasource_id\":\"$DS\",\"sql\":\"SELECT COUNT(*) AS n FROM ssb.customer\"}")
if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/qg_ora_e.json")); assert d["ok"] and d["row_count"]>=1'; then
  ok "Oracle execute COUNT(ssb.customer)"
else
  bad "execute http=$code $(head -c 400 /tmp/qg_ora_e.json)"
fi

code=$(curl -sS -o /tmp/qg_ora_ins.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
  -H 'Content-Type: application/json' \
  -d "{\"datasource_id\":\"$DS\",\"sql\":\"INSERT INTO ssb.customer(c_custkey) VALUES(1)\"}")
[[ "$code" == "400" ]] && ok "Oracle INSERT denied" || bad "INSERT should be 400 got $code"

ok "Faz 8 live smoke PASS"
