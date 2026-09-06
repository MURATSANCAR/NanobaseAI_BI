#!/usr/bin/env bash
# Point https://portal.nanobase.ai/timas/api/ at the Semantic Bridge (:8795).
# Usage: switch-timas-api.sh semantic [--port N]
set -euo pipefail
TARGET="${1:-semantic}"
SITE="${PORTAL_SITE:-/etc/nginx/sites-enabled/portal.nanobase.ai}"
case "$TARGET" in
  semantic) UP="127.0.0.1:${SEMANTIC_BRIDGE_PORT:-8795}" ;;
  *) echo "usage: $0 semantic" >&2; exit 2 ;;
esac
log() { printf '[switch-timas-api] %s\n' "$*"; }
curl -fsS -m 10 "http://${UP}/health" >/dev/null 2>&1 || curl -fsS -m 10 -o /dev/null "http://${UP}/" || { echo "[switch-timas-api] ERROR: ${UP} not answering" >&2; exit 1; }
sudo mkdir -p /etc/nginx/backups
sudo cp "$SITE" "/etc/nginx/backups/$(basename "$SITE").bak-$(date +%Y%m%d%H%M%S)"
sudo python3 - "$SITE" "$UP" <<'PY'
import re, sys
site, up = sys.argv[1], sys.argv[2]
s = open(site, encoding="utf-8").read()
m = re.search(r"(location /timas/api/ \{.*?proxy_pass http://)([^/]+)(/api/;)", s, re.S)
assert m, "location /timas/api/ block not found"
if m.group(2) == up:
    print("already", up)
else:
    s = s[: m.start(2)] + up + s[m.end(2):]
    open(site, "w", encoding="utf-8").write(s)
    print("switched", m.group(2), "->", up)
PY
sudo nginx -t && sudo nginx -s reload
sleep 1
curl -s -o /dev/null -w "  /timas/api/v1/engine -> %{http_code}\n" -m 20 https://portal.nanobase.ai/timas/api/v1/engine
log "/timas/api/ now → ${UP} (${TARGET})"
