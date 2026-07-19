#!/usr/bin/env bash
# Faz 9: SAP HANA / OData smoke (skips if secrets missing).
set -euo pipefail
BASE="${QG_BASE:-http://127.0.0.1:8792}"
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
MAP="${SECRETS}/sap-ro.datasources.json"

ok() { printf 'OK  %s\n' "$*"; }
skip() { printf 'SKIP %s\n' "$*"; exit 0; }
bad() { printf 'FAIL %s\n' "$*"; exit 1; }

curl -fsS "$BASE/health" >/tmp/qg_sap_h.json || bad "health"
python3 - <<'PY'
import json
d=json.load(open("/tmp/qg_sap_h.json"))
assert d.get("odata_ready") is True
print("hana_driver", d.get("hana_driver"), "odata_ready", d.get("odata_ready"), "datasources", d.get("datasources"))
PY
ok "gateway health (odata_ready)"

[[ -f "$MAP" ]] || skip "no $MAP — SAP connector ready, awaiting credentials"

python3 - <<'PY'
import json,urllib.request
d=json.load(urllib.request.urlopen("http://127.0.0.1:8792/api/v1/query/datasources"))
drivers={}
for x in d.get("datasources") or []:
    drivers[x["id"]]=(x.get("driver") or "").lower()
open("/tmp/qg_sap_ds.json","w").write(json.dumps(drivers))
print(drivers)
assert any(v in ("hana","odata") for v in drivers.values()), drivers
PY
ok "SAP datasource(s) registered"

# OData path validation against first odata source (no network if allowlist rejects bad entity)
ODATA_ID=$(python3 -c 'import json;d=json.load(open("/tmp/qg_sap_ds.json"));print(next((k for k,v in d.items() if v=="odata"),""))')
if [[ -n "$ODATA_ID" ]]; then
  code=$(curl -sS -o /tmp/qg_od_bad.json -w '%{http_code}' -X POST "$BASE/api/v1/query/validate" \
    -H 'Content-Type: application/json' \
    -d "{\"datasource_id\":\"$ODATA_ID\",\"sql\":\"EvilEntity\"}")
  if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/qg_od_bad.json")); assert d.get("ok") is False'; then
    ok "OData allowlist rejects unknown entity"
  else
    bad "OData allowlist check failed ($code)"
  fi
fi

HANA_ID=$(python3 -c 'import json;d=json.load(open("/tmp/qg_sap_ds.json"));print(next((k for k,v in d.items() if v=="hana"),""))')
if [[ -n "$HANA_ID" ]]; then
  code=$(curl -sS -o /tmp/qg_hana_ins.json -w '%{http_code}' -X POST "$BASE/api/v1/query/validate" \
    -H 'Content-Type: application/json' \
    -d "{\"datasource_id\":\"$HANA_ID\",\"sql\":\"INSERT INTO sflight VALUES(1)\"}")
  if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/qg_hana_ins.json")); assert d.get("ok") is False'; then
    ok "HANA INSERT rejected at validate"
  else
    # execute path also rejects
    code2=$(curl -sS -o /tmp/qg_hana_ins2.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
      -H 'Content-Type: application/json' \
      -d "{\"datasource_id\":\"$HANA_ID\",\"sql\":\"INSERT INTO sflight VALUES(1)\"}")
    [[ "$code2" == "400" ]] && ok "HANA INSERT denied on execute" || bad "HANA INSERT not denied"
  fi
fi

ok "Faz 9 connector checks PASS (live fetch depends on network/creds)"
