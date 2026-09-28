#!/usr/bin/env bash
# NanobaseAI Destek kurulumu / güncellemesi (test sunucusu ya da müşteri VM'i).
#
#   apps/destek/scripts/install.sh <kaynak: git archive main'in apps/destek'i> <commit sha>
#
# Ne yapar: imajı derler → .env yoksa üretir → yığını kaldırır → site yoksa kurar,
# varsa göç eder → marka/bölge ayarları ve model tanımı → sağlık ve kurulum denetimi.
# Veri silmez: site, veritabanı ve dosyalar docker volume'larındadır.
set -euo pipefail

SRC=$(cd "${1:?kaynak dizini}" && pwd)
SHA=${2:?commit sha}
SHORT=${SHA:0:8}
DEST=${DESTEK_DIR:-/data/nanobaseai/destek}
PROJECT=nanobase-destek
SITE=${SITE_NAME:-destek}
PUBLIC_URL=${PUBLIC_URL:-https://portal.nanobase.ai:8446}
# Panel modele LLM kapısından gider (köprünün OpenAI uyumlu girişi; nginx deploy/nginx-destek-llm.conf).
LLM_BASE=${LLM_BASE:-https://portal.nanobase.ai/destek-llm/v1}
LLM_KEY_FILE=${LLM_KEY_FILE:-/etc/nanobase/destek-llm.key}
ADMIN_FILE=${ADMIN_FILE:-/etc/nanobase/destek-admin.txt}
AD_FILE=${AD_FILE:-/etc/nanobase/timas-ad.json}
# Portal oturumuyla otomatik giriş: portal giriş servisi (www-data) ile Destek sitesinin ortak imza anahtarı.
SSO_FILE=${SSO_FILE:-/etc/nanobase/destek-sso.key}
BRIDGE_ENV=${BRIDGE_ENV:-/etc/nanobase/semantic-bridge.env}
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/frappe-apps/nanobase_brand/nanobase_brand/__init__.py")
IMAGE="nanobase-destek:${VERSION}-${SHORT}"

say() { printf '\n== %s\n' "$*"; }

say "Mac artığı denetimi (kaynak)"
n=$(find "$SRC" -name '._*' -type f -not -path '*/node_modules/*' | wc -l)
[ "$n" -eq 0 ] || { echo "kaynakta $n adet ._* var; git archive ile yeniden al"; exit 1; }

say "İmaj: $IMAGE"
docker build -f "$SRC/docker/Containerfile" --build-arg "CODE_VERSION=$SHA" -t "$IMAGE" "$SRC"

say "Yapılandırma: $DEST"
sudo mkdir -p "$DEST" && sudo chown "$(id -u):$(id -g)" "$DEST"
cp "$SRC/docker/compose.yaml" "$DEST/compose.yaml"
if [ ! -f "$DEST/.env" ]; then
  umask 077
  printf 'DESTEK_IMAGE=%s\nSITE_NAME=%s\nHTTP_PORT=8447\nDB_ROOT_PASSWORD=%s\n' \
    "$IMAGE" "$SITE" "$(openssl rand -hex 24)" > "$DEST/.env"
fi
sed -i "s|^DESTEK_IMAGE=.*|DESTEK_IMAGE=$IMAGE|" "$DEST/.env"
set -a; . "$DEST/.env"; set +a

dc() { docker compose -p "$PROJECT" --env-file "$DEST/.env" -f "$DEST/compose.yaml" "$@"; }

say "Yığın"
dc up -d --remove-orphans
for _ in $(seq 60); do dc exec -T backend true 2>/dev/null && break; sleep 2; done

if dc exec -T backend test -d "sites/$SITE"; then
  say "Site var → göç"
  dc exec -T backend bench --site "$SITE" migrate
else
  say "Site yok → kurulum"
  if ! sudo test -f "$ADMIN_FILE"; then
    openssl rand -base64 18 | sudo tee "$ADMIN_FILE" >/dev/null
    sudo chmod 600 "$ADMIN_FILE"
  fi
  ADMIN_PW=$(sudo cat "$ADMIN_FILE")
  dc exec -T backend bench new-site "$SITE" \
    --mariadb-user-host-login-scope='%' \
    --db-root-username root --db-root-password "$DB_ROOT_PASSWORD" \
    --admin-password "$ADMIN_PW" \
    --install-app helpdesk --install-app flow --install-app nanobase_brand \
    --set-default
fi

say "Site ayarları"
dc exec -T backend bench --site "$SITE" set-config host_name "$PUBLIC_URL"
dc exec -T backend bench --site "$SITE" set-config server_script_enabled 1
dc exec -T backend bench --site "$SITE" execute nanobase_brand.install.apply

if sudo test -f "$LLM_KEY_FILE"; then
  say "Model tanımı"
  # Anahtar dosyadan okunur, standart girişten gider: komut satırında görünmez.
  sudo python3 -c 'import json,sys; print(json.dumps({"base_url": sys.argv[1], "api_key": open(sys.argv[2]).read().strip()}))' "$LLM_BASE" "$LLM_KEY_FILE" \
    | dc exec -T backend bench --site "$SITE" execute nanobase_brand.ai.ensure_model >/dev/null
else
  echo "UYARI: $LLM_KEY_FILE yok; yapay zekâ paneli model olmadan açılır"
fi
if sudo test -f "$AD_FILE"; then
  say "AD girişi (NTLM)"
  # Portal girişinin AD dosyası + köprünün yönetici grubu/listesi; standart girişten gider.
  ADMIN_GROUP=$(sudo sed -n 's/^TIMAS_ADMIN_GROUP=//p' "$BRIDGE_ENV" 2>/dev/null | tail -1)
  ADMIN_USERS=$(sudo sed -n 's/^TIMAS_ADMIN_USERS=//p' "$BRIDGE_ENV" 2>/dev/null | tail -1)
  sudo python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); d["admin_group"]=sys.argv[2] or "Administrators"; d["admin_users"]=sys.argv[3] or "zekiai,timasai,muratsancar"; print(json.dumps(d))' \
    "$AD_FILE" "$ADMIN_GROUP" "$ADMIN_USERS" \
    | dc exec -T backend bench --site "$SITE" execute nanobase_brand.ad.ensure_ldap
else
  echo "UYARI: $AD_FILE yok; AD girişi kapalı"
fi
say "Portal oturumuyla giriş (SSO anahtarı)"
if ! sudo test -f "$SSO_FILE"; then
  openssl rand -hex 32 | sudo tee "$SSO_FILE" >/dev/null
fi
sudo chown root:www-data "$SSO_FILE" && sudo chmod 640 "$SSO_FILE"
sudo cat "$SSO_FILE" | dc exec -T backend bench --site "$SITE" execute nanobase_brand.sso.set_secret >/dev/null

say "Giden e-posta (Gmail, zeki@)"
# SMTP ayarı köprünün yönetim ayarlarından (ALERT_SMTP_*): şifre ekrana, komut satırına ve depoya düşmez.
BRIDGE_PY=${BRIDGE_PY:-/data/nanobaseai/bi/semantic-venv/bin/python}
BRIDGE_SRC=${BRIDGE_SRC:-/data/nanobaseai/bi/frontend/backend}
if [ -x "$BRIDGE_PY" ] && sudo test -f "$BRIDGE_ENV"; then
  sudo env PYTHONPATH="$BRIDGE_SRC" "$BRIDGE_PY" -c '
import json, os, sys
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"\x27": v = v[1:-1]
        os.environ.setdefault(k.strip(), v)
from semantic_bridge import admin as a
c = {k: a.conf("ALERT_SMTP_" + k.upper()) for k in ("host", "port", "user", "password")}
if not (c["user"] and c["password"]): sys.exit(3)
print(json.dumps(c))' "$BRIDGE_ENV" \
    | dc exec -T backend bench --site "$SITE" execute nanobase_brand.eposta.ensure_outgoing >/dev/null \
    && echo "giden e-posta hesabı hazır" || echo "UYARI: giden e-posta ayarlanamadı (köprüde ALERT_SMTP_* yok ya da SMTP girişi reddetti)"
else
  echo "UYARI: köprü ayarı yok; giden e-posta ayarlanmadı"
fi

dc exec -T backend bench --site "$SITE" clear-cache
dc restart backend websocket queue-short queue-long scheduler frontend >/dev/null

say "Denetim"
for _ in $(seq 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HTTP_PORT}/api/method/ping") && [ "$code" = 200 ] && break
  sleep 2
done
echo "ping: $code"
echo "imaj: $(docker inspect "${PROJECT}-backend-1" --format '{{.Config.Image}}')"
echo "kod sürümü: $(dc exec -T backend printenv DESTEK_CODE_VERSION)"
echo "._* (hedef): $(find "$DEST" -name '._*' -type f | wc -l)"
echo "._* (konteyner): $(dc exec -T backend bash -c "find apps -name '._*' -type f | wc -l")"
