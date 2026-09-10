#!/usr/bin/env bash
# Point every https://portal.nanobase.ai/timas/api* location at one engine upstream.
#
# The site has more than one location for this API (the general /timas/api/ prefix plus narrower,
# rate-limited regex locations such as /timas/api/v1/ask). Rewriting only one of them would leave the
# cockpit talking to two different engines at once, so this script moves them together or not at all.
#
# Usage: switch-timas-api.sh semantic [--dry-run]
#        switch-timas-api.sh --to 127.0.0.1:8795
set -euo pipefail
TARGET="${1:-semantic}"
DRY=0
UP=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --to) shift; UP="${1:-}" ;;
    semantic) UP="127.0.0.1:${SEMANTIC_BRIDGE_PORT:-8795}" ;;
    *) if [[ -z "$UP" ]]; then echo "usage: $0 semantic|--to host:port [--dry-run]" >&2; exit 2; fi ;;
  esac
  shift || true
done
[[ -n "$UP" ]] || UP="127.0.0.1:${SEMANTIC_BRIDGE_PORT:-8795}"
SITE="${PORTAL_SITE:-/etc/nginx/sites-enabled/portal.nanobase.ai}"

log() { printf '[switch-timas-api] %s\n' "$*"; }

# Refuse to point traffic at something that is not answering.
curl -fsS -m 10 "http://${UP}/health" >/dev/null 2>&1 || { echo "[switch-timas-api] ERROR: ${UP} is not healthy" >&2; exit 1; }

TRANSFORM='
import re, sys
site, up, dry = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
s = open(site, encoding="utf-8").read()
# Every location block whose path mentions /timas/api, including regex locations.
blocks = list(re.finditer(r"(?m)^[ \t]*location[^\n{]*?/timas/api[^\n{]*\{", s))
if not blocks:
    print("no /timas/api location found"); sys.exit(3)
changed, seen = [], 0
out, cursor = [], 0
for b in blocks:
    # the block body: from the opening brace to the matching close at the same indent
    start = b.end()
    depth, i = 1, start
    while i < len(s) and depth:
        if s[i] == "{": depth += 1
        elif s[i] == "}": depth -= 1
        i += 1
    body = s[start:i]
    def repl(m):
        global seen
        seen += 1
        if m.group(2) == up:
            return m.group(0)
        changed.append((m.group(2), m.group(3) or ""))
        return m.group(1) + up + (m.group(3) or "")
    new_body = re.sub(r"(proxy_pass\s+http://)([^/;\s]+)([^;\s]*)", repl, body)
    out.append(s[cursor:start]); out.append(new_body); cursor = i
out.append(s[cursor:])
result = "".join(out)
print("locations:", len(blocks), "| proxy_pass seen:", seen, "| rewritten:", len(changed))
for old, path in changed:
    print("   ", old, "->", up, path)
if not dry:
    open(site, "w", encoding="utf-8").write(result)
sys.exit(0 if changed or seen else 4)
'

if [[ "$DRY" == "1" ]]; then
  python3 -c "$TRANSFORM" "$SITE" "$UP" 1
  exit 0
fi
sudo mkdir -p /etc/nginx/backups
BACKUP="/etc/nginx/backups/$(basename "$SITE").bak-$(date +%Y%m%d%H%M%S)"
sudo cp "$SITE" "$BACKUP"
log "backup: $BACKUP"
sudo python3 -c "$TRANSFORM" "$SITE" "$UP" 0
if ! sudo nginx -t; then
  log "nginx config invalid — restoring ${BACKUP}"
  sudo cp "$BACKUP" "$SITE"
  sudo nginx -t
  exit 1
fi
sudo nginx -s reload
sleep 1
for path in /timas/api/v1/engine /timas/api/v1/ask; do
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 20 "https://portal.nanobase.ai${path}" || true)"
  printf '  %s -> %s\n' "$path" "$code"
done
log "/timas/api* now → ${UP}; rollback: sudo cp ${BACKUP} ${SITE} && sudo nginx -s reload"
