#!/usr/bin/env bash
# Verify Neon erp/sigorta through Query Gateway.
set -euo pipefail
BASE="${QG_BASE:-http://127.0.0.1:8792}"
fail=0
ok() { printf 'OK  %s\n' "$*"; }
bad() { printf 'FAIL %s\n' "$*"; fail=1; }

curl -fsS "$BASE/health" >/tmp/qg_neon_h.json || bad "health"
python3 - <<'PY' || bad "erp/sigorta not registered"
import json
d=json.load(open("/tmp/qg_neon_h.json"))
ds=set(d.get("datasources") or [])
assert "erp" in ds and "sigorta" in ds, ds
print("datasources", sorted(ds))
PY
[[ $fail -eq 0 ]] && ok "erp+sigorta registered"

# Find a real table from allowlist via a simple information-free probe:
# Gateway rejects unknown tables; use first table from validate of SELECT 1 — instead
# execute a known safe pattern: SELECT current_database()
for sid in erp sigorta; do
  code=$(curl -sS -o /tmp/qg_neon_db.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
    -H 'Content-Type: application/json' \
    -d "{\"datasource_id\":\"$sid\",\"sql\":\"SELECT current_database() AS db\"}")
  # current_database() has no table — allowlist may still pass if no tables referenced
  if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/qg_neon_db.json")); assert d.get("ok")'; then
    ok "$sid SELECT current_database()"
  else
    bad "$sid current_database http=$code $(head -c 200 /tmp/qg_neon_db.json)"
  fi

  code=$(curl -sS -o /tmp/qg_neon_ins.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
    -H 'Content-Type: application/json' \
    -d "{\"datasource_id\":\"$sid\",\"sql\":\"INSERT INTO pg_shadow DEFAULT VALUES\"}")
  [[ "$code" == "400" ]] && ok "$sid INSERT denied" || bad "$sid INSERT should be 400 got $code"
done

# Table smoke: pick first allowlisted table from secrets map
python3 - <<'PY' || bad "table smoke"
import json,urllib.request
from pathlib import Path
cfg=json.loads(Path("/data/nanobaseai/bi/secrets/neon-ro.datasources.json").read_text())
for sid, s in (cfg.get("sources") or {}).items():
    tables=[t for t in (s.get("allowed_tables") or []) if "." not in t]
    if not tables:
        print("no tables", sid); continue
    t=tables[0]
    body=json.dumps({"datasource_id":sid,"sql":f"SELECT * FROM {t}"}).encode()
    req=urllib.request.Request("http://127.0.0.1:8792/api/v1/query/execute", data=body, headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d=json.load(r)
        assert d.get("ok"), d
        print("OK ", sid, "SELECT * FROM", t, "rows", d.get("row_count"))
    except Exception as e:
        raise SystemExit(f"FAIL {sid} {t}: {e}")
PY

exit "$fail"
