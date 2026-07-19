#!/usr/bin/env bash
# Faz 9: SAP HANA / OData smoke (offline policy always; live skips if secrets missing).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BASE="${QG_BASE:-http://127.0.0.1:8792}"
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
MAP="${SECRETS}/sap-ro.datasources.json"
PY="${NANOBASE_PYTHON:-$ROOT/backend/.venv/bin/python}"
export PYTHONPATH="${ROOT}/backend${PYTHONPATH:+:$PYTHONPATH}"

ok() { printf 'OK  %s\n' "$*"; }
skip() { printf 'SKIP %s\n' "$*"; exit 0; }
bad() { printf 'FAIL %s\n' "$*"; exit 1; }

# Offline policy smoke (always)
"$PY" - <<'PY' || bad "offline SAP policy smoke"
from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.contracts.datasource import ODataDatasourceConfig
from query_gateway.infrastructure.sap.contracts.query import ODataFilter, ODataLogicalPlan
from query_gateway.infrastructure.sap.odata.query_builder import build_odata_request
from query_gateway.infrastructure.sap.hana.parser_policy import enforce_hana_sql_policy
from query_gateway.infrastructure.sap.hana.profile import validate_hana_username

cfg = ODataDatasourceConfig(
    datasource_id="t",
    base_url="https://s4.example.internal/sap/opu/odata/sap/API_JOURNALENTRYITEM_SRV",
    allowed_services=["API_JOURNALENTRYITEM_SRV"],
    allowed_entity_sets=["JournalEntryItem"],
    source_status="PUBLISHED",
)
plan = ODataLogicalPlan(
    source_type="SAP_ODATA",
    service="API_JOURNALENTRYITEM_SRV",
    entity_set="JournalEntryItem",
    select=["CompanyCode"],
    filters=[ODataFilter("CompanyCode", "EQ", "1000")],
    top=10,
)
built = build_odata_request(plan, cfg)
assert built["method"] == "GET"

for bad_plan in [
    ODataLogicalPlan("SAP_ODATA", "API_JOURNALENTRYITEM_SRV", "Evil", ["CompanyCode"], top=10),
    ODataLogicalPlan("SAP_ODATA", "API_JOURNALENTRYITEM_SRV", "JournalEntryItem", [], top=10),
    ODataLogicalPlan("SAP_ODATA", "API_JOURNALENTRYITEM_SRV", "../x", ["CompanyCode"], top=10),
]:
    try:
        build_odata_request(bad_plan, cfg)
        raise SystemExit("expected reject")
    except GatewayError:
        pass

for sql in [
    "INSERT INTO T VALUES (1)",
    "SELECT * FROM ACDOCA",
    "CALL P()",
    "SELECT * FROM SYS.TABLES",
]:
    try:
        enforce_hana_sql_policy(sql)
        raise SystemExit(f"expected reject: {sql}")
    except GatewayError:
        pass

try:
    validate_hana_username("SYSTEM")
    raise SystemExit("SYSTEM user should fail")
except GatewayError:
    pass

print("offline SAP policy OK")
PY
ok "offline OData/HANA policy smoke"

curl -fsS "$BASE/health" >/tmp/qg_sap_h.json 2>/dev/null || skip "gateway not running — offline checks PASS"
"$PY" - <<'PY'
import json
d=json.load(open("/tmp/qg_sap_h.json"))
assert d.get("odata_ready") is True
print("hana_driver", d.get("hana_driver"), "odata_ready", d.get("odata_ready"), "datasources", d.get("datasources"))
PY
ok "gateway health (odata_ready)"

[[ -f "$MAP" ]] || skip "no $MAP — SAP connector ready, awaiting credentials"

"$PY" - <<'PY'
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

ODATA_ID=$("$PY" -c 'import json;d=json.load(open("/tmp/qg_sap_ds.json"));print(next((k for k,v in d.items() if v=="odata"),""))')
if [[ -n "$ODATA_ID" ]]; then
  code=$(curl -sS -o /tmp/qg_od_bad.json -w '%{http_code}' -X POST "$BASE/api/v1/query/validate" \
    -H 'Content-Type: application/json' \
    -d "{\"datasource_id\":\"$ODATA_ID\",\"sql\":\"EvilEntity\"}")
  if [[ "$code" == "200" ]] && "$PY" -c 'import json;d=json.load(open("/tmp/qg_od_bad.json")); assert d.get("ok") is False'; then
    ok "OData allowlist rejects unknown entity"
  else
    bad "OData allowlist check failed ($code)"
  fi
fi

HANA_ID=$("$PY" -c 'import json;d=json.load(open("/tmp/qg_sap_ds.json"));print(next((k for k,v in d.items() if v=="hana"),""))')
if [[ -n "$HANA_ID" ]]; then
  code=$(curl -sS -o /tmp/qg_hana_ins.json -w '%{http_code}' -X POST "$BASE/api/v1/query/validate" \
    -H 'Content-Type: application/json' \
    -d "{\"datasource_id\":\"$HANA_ID\",\"sql\":\"INSERT INTO sflight VALUES(1)\"}")
  if [[ "$code" == "200" ]] && "$PY" -c 'import json;d=json.load(open("/tmp/qg_hana_ins.json")); assert d.get("ok") is False'; then
    ok "HANA INSERT rejected at validate"
  else
    code2=$(curl -sS -o /tmp/qg_hana_ins2.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
      -H 'Content-Type: application/json' \
      -d "{\"datasource_id\":\"$HANA_ID\",\"sql\":\"INSERT INTO sflight VALUES(1)\"}")
    [[ "$code2" == "400" ]] && ok "HANA INSERT denied on execute" || bad "HANA INSERT not denied"
  fi
fi

ok "Faz 9 connector checks PASS (live fetch depends on network/creds)"
