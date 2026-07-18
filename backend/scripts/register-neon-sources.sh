#!/usr/bin/env bash
# Register Neon ERP + Sigorta datasources into a running DB-GPT (:5670).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export DBGPT_BASE="${DBGPT_BASE:-http://127.0.0.1:5670}"
export BI_SOURCES_FILE="${BI_SOURCES_FILE:-$ROOT/configs/sources/local/connection.local.json}"

if [[ ! -f "$BI_SOURCES_FILE" ]]; then
  echo "error: sources file missing: $BI_SOURCES_FILE" >&2
  exit 1
fi

python3 - <<'PY'
import json, os, urllib.error, urllib.request

base = os.environ["DBGPT_BASE"].rstrip("/")
path = os.environ["BI_SOURCES_FILE"]
with open(path, encoding="utf-8") as f:
    raw = json.load(f)

sources = raw.get("sources") or {}
errors = []
for sid, s in sources.items():
    pwd = s.get("password") or os.environ.get(f"BI_{sid.upper()}_PASSWORD") or ""
    if not pwd:
        errors.append(f"{sid}: missing password")
        continue
    payload = {
        "db_type": "postgresql",
        "db_name": s.get("id") or sid,
        "db_host": s.get("host"),
        "db_port": int(s.get("port") or 5432),
        "db_user": s.get("username") or "neondb_owner",
        "db_pwd": pwd,
        "comment": s.get("label") or sid,
    }
    last = None
    ok = False
    for url in (f"{base}/api/v1/chat/db/add", f"{base}/api/v2/serve/datasources"):
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode(errors="replace")
                print(f"OK {sid} via {url} → {resp.status} {body[:240]}")
                ok = True
                break
        except Exception as e:
            last = e
    if not ok:
        errors.append(f"{sid}: {last}")

if errors:
    print("ERRORS:", file=__import__("sys").stderr)
    for e in errors:
        print(" ", e, file=__import__("sys").stderr)
    raise SystemExit(1)
print("Done — datasources registered.")
PY
