#!/usr/bin/env bash
# Verify Neon RO datasources (any ids in neon-ro.datasources.json) through Query Gateway.
set -euo pipefail
BASE="${QG_BASE:-http://127.0.0.1:8792}"
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
fail=0
ok() { printf 'OK  %s\n' "$*"; }
bad() { printf 'FAIL %s\n' "$*"; fail=1; }

curl -fsS "$BASE/health" >/tmp/qg_neon_h.json || bad "health"

python3 - <<PY || bad "neon map vs gateway"
import json
from pathlib import Path
h=json.load(open("/tmp/qg_neon_h.json"))
qg=set(h.get("datasources") or [])
neon_path=Path("${SECRETS}")/"neon-ro.datasources.json"
assert neon_path.is_file(), f"missing {neon_path}"
neon=set((json.loads(neon_path.read_text()).get("sources") or {}).keys())
assert neon, "neon-ro map empty"
missing=sorted(neon-qg)
assert not missing, f"gateway missing {missing}; have {sorted(qg)}"
print("datasources", sorted(neon))
open("/tmp/qg_neon_sids.txt","w").write("\n".join(sorted(neon)))
PY
[[ $fail -eq 0 ]] && ok "neon map registered in gateway"

while IFS= read -r sid; do
  [[ -z "$sid" ]] && continue
  code=$(curl -sS -o /tmp/qg_neon_db.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
    -H 'Content-Type: application/json' \
    -d "{\"datasource_id\":\"$sid\",\"sql\":\"SELECT current_database() AS db\"}")
  if [[ "$code" == "200" ]] && python3 -c 'import json;d=json.load(open("/tmp/qg_neon_db.json")); assert d.get("ok")'; then
    ok "$sid SELECT current_database()"
  else
    bad "$sid current_database http=$code $(head -c 200 /tmp/qg_neon_db.json)"
  fi

  code=$(curl -sS -o /tmp/qg_neon_ins.json -w '%{http_code}' -X POST "$BASE/api/v1/query/execute" \
    -H 'Content-Type: application/json' \
    -d "{\"datasource_id\":\"$sid\",\"sql\":\"INSERT INTO pg_shadow DEFAULT VALUES\"}")
  [[ "$code" == "400" ]] && ok "$sid INSERT denied" || bad "$sid INSERT should be 400 got $code"
done < /tmp/qg_neon_sids.txt

# Table smoke: pick first allowlisted table from secrets map
python3 - <<'PY' || bad "table smoke"
import json,urllib.request
from pathlib import Path
import os
cfg=json.loads(Path(os.environ.get("SECRETS_ROOT","/data/nanobaseai/bi/secrets")).joinpath("neon-ro.datasources.json").read_text())
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
