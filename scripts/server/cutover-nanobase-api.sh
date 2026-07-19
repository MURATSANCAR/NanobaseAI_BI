#!/usr/bin/env bash
# Faz 4: point nginx BI API upstream to nanobase_api :8790 and stop bridge.
set -euo pipefail

NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-enabled/portal.nanobase.ai}"
BACKUP="/tmp/portal.nanobase.ai.bak.$(date +%Y%m%d%H%M%S)"

log() { printf '[cutover] %s\n' "$*"; }

# Ensure API is healthy
curl -fsS http://127.0.0.1:8790/health >/dev/null || {
  log "nanobase-bi-api not healthy — starting"
  sudo systemctl restart nanobase-bi-api
  sleep 2
  curl -fsS http://127.0.0.1:8790/health >/dev/null
}

sudo cp -a "$NGINX_SITE" "$BACKUP"
log "nginx backup → $BACKUP"

# Switch upstream 8789 → 8790 (in-place, no sites-enabled *.bak)
sudo python3 - <<'PY'
from pathlib import Path
p = Path("/etc/nginx/sites-enabled/portal.nanobase.ai")
text = p.read_text()
text2 = text.replace("server 127.0.0.1:8789;", "server 127.0.0.1:8790;")
text2 = text2.replace("BI APIs → DB-GPT bridge (:8789)", "BI APIs → nanobase_api (:8790)")
if text == text2 and "127.0.0.1:8790" not in text:
    raise SystemExit("upstream replace failed — 8789 not found")
p.write_text(text2)
print("nginx upstream updated")
PY

# Remove accidental nginx backup configs inside sites-enabled
sudo rm -f /etc/nginx/sites-enabled/portal.nanobase.ai.bak /etc/nginx/sites-enabled/*.bak

sudo nginx -t
sudo systemctl reload nginx

# Verify public path
code=$(curl -sS -o /tmp/bi_api_health.json -w '%{http_code}' https://portal.nanobase.ai/bi-api/health || true)
log "https://portal.nanobase.ai/bi-api/health → HTTP $code"
cat /tmp/bi_api_health.json; echo

# Stop legacy bridge (keep unit installed for rollback)
sudo systemctl disable --now nanobase-bi-bridge || true
log "nanobase-bi-bridge stopped/disabled"

# Smoke
curl -fsS https://portal.nanobase.ai/bi-api/api/v1/bi/status | python3 -m json.tool | head -20
curl -fsS https://portal.nanobase.ai/bi-api/api/v1/bi/sources | python3 -c \
  'import sys,json; d=json.load(sys.stdin); print("active", d.get("active_id"), "n", len(d.get("sources") or []))'

log "Faz 4 cutover complete. Rollback: sudo cp $BACKUP $NGINX_SITE && sudo systemctl reload nginx && sudo systemctl enable --now nanobase-bi-bridge"
