#!/usr/bin/env bash
# /timas için nginx kimlik doğrulama (HTTP Basic) + hız sınırı. Idempotent.
#   kullanıcı: timas  · parola: ${SECRETS}/timas-portal.password (yoksa üretilir, asla stdout'a yazılmaz)
#   hız: /timas/api/v1/ask 6 istek/dk (patlama 3), /timas/api/ 120 istek/dk (patlama 30), IP başına
set -euo pipefail
SITE="${PORTAL_SITE:-/etc/nginx/sites-enabled/portal.nanobase.ai}"
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
HTPASSWD=/etc/nginx/htpasswd-timas
USER_NAME="${TIMAS_USER:-timas}"
log() { printf '[deploy-timas-auth] %s\n' "$*"; }

# 1) parola dosyası
umask 077
if [[ ! -s "${SECRETS}/timas-portal.password" ]]; then
  openssl rand -base64 24 | tr -d '/+=' | cut -c1-20 > "${SECRETS}/timas-portal.password"
  log "yeni parola üretildi → ${SECRETS}/timas-portal.password"
fi
PW="$(tr -d '\n' < "${SECRETS}/timas-portal.password")"
HASH="$(openssl passwd -apr1 "$PW")"
printf '%s:%s\n' "$USER_NAME" "$HASH" | sudo tee "$HTPASSWD" >/dev/null
sudo chmod 640 "$HTPASSWD"; sudo chown root:www-data "$HTPASSWD"

# 2) nginx: zone (http seviyesi = site dosyasının tepesi) + location içi kurallar
sudo mkdir -p /etc/nginx/backups
sudo cp "$SITE" "/etc/nginx/backups/$(basename "$SITE").bak-auth-$(date +%Y%m%d%H%M%S)"
sudo python3 - "$SITE" "$HTPASSWD" <<'PY'
import re, sys
site, htp = sys.argv[1], sys.argv[2]
s = open(site, encoding="utf-8").read()
zone = ("# TİMAŞ cockpit hız sınırı (IP başına): LLM'e giden /ask dar, diğer API geniş\n"
        "limit_req_zone $binary_remote_addr zone=timas_ask:10m rate=6r/m;\n"
        "limit_req_zone $binary_remote_addr zone=timas_api:10m rate=120r/m;\n\n")
if "zone=timas_ask" not in s:
    s = zone + s
auth = ("        auth_basic \"Timaş Finans\";\n"
        "        auth_basic_user_file %s;\n" % htp)
# /timas/api/ bloğu: auth + api limiti; /ask için ayrı, daha dar location
api_block = re.search(r"(    location /timas/api/ \{\n)(.*?)(\n    \}\n)", s, re.S)
assert api_block, "/timas/api/ bloğu yok"
body = api_block.group(2)
if "auth_basic" not in body:
    body = auth + "        limit_req zone=timas_api burst=30 nodelay;\n        limit_req_status 429;\n" + body
    s = s[:api_block.start(2)] + body + s[api_block.end(2):]
if "location /timas/api/v1/ask" not in s:
    ask_loc = ("    location ~ ^/timas/api/v1/ask(_agent)?$ {\n"
               + auth +
               "        limit_req zone=timas_ask burst=3 nodelay;\n"
               "        limit_req_status 429;\n"
               "        rewrite ^/timas/(.*)$ /$1 break;\n"
               "        proxy_pass http://127.0.0.1:8794;\n"
               "        proxy_http_version 1.1;\n"
               "        proxy_set_header Host $host;\n"
               "        proxy_set_header X-Real-IP $remote_addr;\n"
               "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
               "        proxy_set_header X-Forwarded-Proto $scheme;\n"
               "        proxy_set_header Connection \"\";\n"
               "        proxy_read_timeout 600s;\n"
               "        proxy_send_timeout 600s;\n"
               "        proxy_buffering off;\n"
               "    }\n")
    # /timas/api/ bloğunun ÖNÜNE koy (regex location'lar prefix'lerden önce değerlendirilir ama sıralı dursun)
    s = s.replace("    location /timas/api/ {", ask_loc + "    location /timas/api/ {", 1)
ask_blk = re.search(r"(    location ~ \^/timas/api/v1/ask\(_agent\)\?\$ \{\n)(.*?)(\n    \}\n)", s, re.S)
if ask_blk and "rewrite ^/timas/" not in ask_blk.group(2):
    s = s[:ask_blk.start(2)] + "        rewrite ^/timas/(.*)$ /$1 break;\n" + ask_blk.group(2) + s[ask_blk.end(2):]
static = re.search(r"(    location /timas/ \{\n)(.*?)(\n    \}\n)", s, re.S)
assert static, "/timas/ bloğu yok"
if "auth_basic" not in static.group(2):
    s = s[:static.start(2)] + auth + static.group(2) + s[static.end(2):]
open(site, "w", encoding="utf-8").write(s)
print("nginx site güncellendi")
PY
sudo nginx -t && sudo nginx -s reload
sleep 1
log "doğrulama"
printf '  kimliksiz /timas/          → %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -m 15 https://portal.nanobase.ai/timas/)"
printf '  kimlikli  /timas/          → %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -m 15 -u "${USER_NAME}:${PW}" https://portal.nanobase.ai/timas/)"
printf '  kimlikli  /timas/api/v1/engine → %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -m 15 -u "${USER_NAME}:${PW}" https://portal.nanobase.ai/timas/api/v1/engine)"
codes=""; for i in $(seq 1 12); do codes="$codes $(curl -s -o /dev/null -w '%{http_code}' -m 5 -u "${USER_NAME}:${PW}" -X POST https://portal.nanobase.ai/timas/api/v1/ask -H 'Content-Type: application/json' -d '{"question":""}')"; done
log "  /ask 12 hızlı istek →$codes  (422 = geçti, 429 = sınırlandı)"
log "hazır — kullanıcı '${USER_NAME}', parola dosyası ${SECRETS}/timas-portal.password"
