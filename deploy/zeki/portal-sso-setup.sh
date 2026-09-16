#!/usr/bin/env bash
# Zeki AI sohbet ↔ portal SSO kurulumu. nanobase-direct üzerinde çalıştırılır.
# Üç adım: (1) nginx yolu, (2) giriş servisini güncelle, (3) chat servis hesabı + config.
# Her adım idempotent; nginx yalnız `nginx -t` geçerse yeniden yüklenir.
set -euo pipefail

REPO="${REPO:-$HOME/NonobaseAI-BI}"          # portal-login/server.py buradan alınır
CHAT_COMPOSE="${CHAT_COMPOSE:-$HOME/zeki-chat/deploy/zeki}"
SITE=/etc/nginx/sites-enabled/portal.nanobase.ai
CHATJSON=/etc/nanobase/zeki-chat.json

echo "== 1/3 nginx =="
sudo tee /etc/nginx/conf.d/zeki-chat-upgrade.conf >/dev/null <<'EOF'
map $http_upgrade $zeki_connection_upgrade {
    default upgrade;
    ""      close;
}
EOF
sudo python3 - "$SITE" <<'EOF'
import sys
p = sys.argv[1]; s = open(p).read()
if "/timas/sohbet/" in s:
    print("  nginx blogu zaten var")
else:
    block = """    # Zeki AI sohbet (ayri Docker, 127.0.0.1:4000). Portal oturumu olmayan istek gecmez.
    location = /timas/sohbet {
        return 302 /timas/sohbet/;
    }
    location ^~ /timas/sohbet/ {
        set $timas_original_method $request_method;
        auth_request /_timas_session_check;
        error_page 401 = @zeki_chat_login;
        client_max_body_size 0;
        proxy_pass http://127.0.0.1:4000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $zeki_connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_request_buffering off;
        proxy_hide_header X-Powered-By;
    }
    location @zeki_chat_login {
        return 302 /timas/;
    }

"""
    anchor = "    location /timas/ {\n        alias /data/nanobaseai/bi/cockpit/dist/;"
    assert anchor in s, "nginx: /timas/ blogu bulunamadi, elle bakin"
    open(p, "w").write(s.replace(anchor, block + anchor, 1))
    print("  nginx blogu eklendi")
EOF
sudo nginx -t

echo "== 2/3 giris servisi =="
sudo install -m 0644 -o root -g root "$REPO/scripts/server/portal-login/server.py" /opt/timas-login/server.py
sudo systemctl restart timas-login
sleep 1
systemctl is-active timas-login

echo "== 3/3 chat servis hesabi =="
if sudo test -f "$CHATJSON"; then
    echo "  $CHATJSON zaten var, dokunulmadi"
else
    # Chat admin bilgileri compose .env'inden okunur.
    set -a; . "$CHAT_COMPOSE/.env"; set +a
    ADMIN_LOGIN="${ZEKI_ADMIN_USERNAME:-zekiadmin}"
    RESP=$(curl -s http://127.0.0.1:${ZEKI_PORT:-4000}/api/v1/login \
        -d "user=${ADMIN_LOGIN}" --data-urlencode "password=${ZEKI_ADMIN_PASS}")
    UID=$(echo "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["userId"])')
    TOK=$(echo "$RESP" | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["authToken"])')
    [ -n "$UID" ] && [ -n "$TOK" ] || { echo "  chat admin girisi basarisiz: $RESP"; exit 1; }
    umask 077
    printf '{\n  "url": "http://127.0.0.1:%s",\n  "user_id": "%s",\n  "token": "%s",\n  "sso_secret": "%s",\n  "email_domain": "%s"\n}\n' \
        "${ZEKI_PORT:-4000}" "$UID" "$TOK" "$ZEKI_SSO_SECRET" "${ZEKI_EMAIL_DOMAIN:-timas.local}" | sudo tee "$CHATJSON" >/dev/null
    sudo chown root:www-data "$CHATJSON"
    sudo chmod 0640 "$CHATJSON"
    echo "  $CHATJSON yazildi (root:www-data 0640)"
fi

echo "== nginx reload =="
sudo systemctl reload nginx
echo "BITTI. Test: portala AD ile gir, /timas/sohbet/ ac."
