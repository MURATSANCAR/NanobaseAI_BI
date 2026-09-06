#!/usr/bin/env bash
# Host the TİMAŞ cockpit (apps/cockpit) at https://portal.nanobase.ai/timas/
#   static build  → /data/nanobaseai/bi/cockpit/dist   (rsync apps/cockpit/dist/ there first;
#                   build with: VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build)
#   /timas/api/*  → semantic bridge 127.0.0.1:8795/api/*  (loopback only)
# Idempotent: inserts the location block into the portal nginx site once, then nginx -t + reload.
set -euo pipefail
SITE="${PORTAL_SITE:-/etc/nginx/sites-enabled/portal.nanobase.ai}"
DIST="${COCKPIT_DIST:-/data/nanobaseai/bi/cockpit/dist}"
ENGINE="${ENGINE_UPSTREAM:-127.0.0.1:8795}"

log() { printf '[deploy-cockpit] %s\n' "$*"; }
die() { printf '[deploy-cockpit] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "${DIST}/index.html" ]] || die "missing ${DIST}/index.html — rsync apps/cockpit/dist first"
grep -q '/timas/assets/' "${DIST}/index.html" || die "dist was not built with VITE_BASE=/timas/"
curl -fsS -m 10 "http://${ENGINE}/health" >/dev/null || die "semantic bridge not reachable at ${ENGINE}"

if sudo grep -q 'location /timas/ ' "$SITE"; then
  log "nginx block already present in $SITE"
else
  log "inserting /timas block into $SITE (before the /bi block)"
  # Backup OUTSIDE sites-enabled: nginx includes sites-enabled/* and a copy there = duplicate upstreams.
  sudo mkdir -p /etc/nginx/backups
  sudo cp "$SITE" "/etc/nginx/backups/$(basename "$SITE").bak-$(date +%Y%m%d%H%M%S)"
  BLOCK=$(cat <<NGX
    # TİMAŞ Finans & Bütçe Masası (apps/cockpit) — https://portal.nanobase.ai/timas/
    # Static build under ${DIST}; /timas/api/* → semantic bridge (${ENGINE}, loopback only).
    location = /timas {
        return 302 /timas/;
    }
    location /timas/api/ {
        proxy_pass http://${ENGINE}/api/;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Connection "";
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_buffering off;
        client_max_body_size 10M;
    }
    location /timas/ {
        alias ${DIST}/;
        try_files \$uri \$uri/ /timas/index.html;
    }

NGX
)
  sudo python3 - "$SITE" "$BLOCK" <<'PY'
import sys
site, block = sys.argv[1], sys.argv[2]
s = open(site, encoding="utf-8").read()
anchor = "    location = /bi {"
assert anchor in s, "anchor '    location = /bi {' not found"
s = s.replace(anchor, block + anchor, 1)
open(site, "w", encoding="utf-8").write(s)
print("inserted")
PY
fi

sudo nginx -t
sudo nginx -s reload   # direct signal: does not go through systemd's (slow) D-Bus
sleep 1
log "checks"
curl -s -o /dev/null -w "  /timas/           -> %{http_code}\n" -m 15 https://portal.nanobase.ai/timas/
curl -s -o /dev/null -w "  /timas/assets     -> %{http_code}\n" -m 15 "https://portal.nanobase.ai$(grep -o '/timas/assets/index-[^"]*\.js' "${DIST}/index.html" | head -1)"
curl -s -m 30 -X POST https://portal.nanobase.ai/timas/api/graphql -H 'Content-Type: application/json' -d '{"query":"{ __typename }"}' | head -c 120; echo
log "cockpit live at https://portal.nanobase.ai/timas/"
