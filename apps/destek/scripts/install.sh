#!/usr/bin/env bash
# NanobaseAI Destek kurulumu / güncellemesi (test sunucusu ya da müşteri VM'i).
#
#   apps/destek/scripts/install.sh <kaynak: git archive main'in apps/destek'i> <commit sha>
#
# Ne yapar: imajı derler → .env yoksa üretir → yığını kaldırır → site yoksa kurar,
# varsa göç eder → marka/bölge ayarları ve model tanımı → sağlık ve kurulum denetimi.
# Veri silmez: site, veritabanı ve dosyalar docker volume'larındadır.
#
# Varsayılanlar test sunucusudur. Müşteri VM'i (192.168.0.55) ortam değişkenleriyle kurulur — örnek: README
# «Müşteri VM'i». VM'de sudo parola ister: sır dosyaları kurulum kullanıcısının okuyabildiği yerdedir,
# sudo yalnız dosya okunamıyorsa ve parolasız (-n) denenir.
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
SSO_GROUP=${SSO_GROUP-www-data}
BRIDGE_ENV=${BRIDGE_ENV:-/etc/nanobase/semantic-bridge.env}
# Ek compose dosyaları ($SRC/docker altında, boşlukla ayrılmış): VM'de compose.bi-net.yaml.
COMPOSE_EXTRA=${COMPOSE_EXTRA:-}
# Siteye yazılacak ek ayarlar (anahtar=değer, boşlukla ayrılmış): VM'de nb_bilgi_bankasi_kapali=1.
SITE_CONFIG_EXTRA=${SITE_CONFIG_EXTRA:-}
# E-posta ayarı: köprünün ayarından (test sunucusu) ya da {"host","port","user","password"} dosyasından (VM).
SMTP_FILE=${SMTP_FILE:-}
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/frappe-apps/nanobase_brand/nanobase_brand/__init__.py")
IMAGE="nanobase-destek:${VERSION}-${SHORT}"

# Sır dosyası: okunabiliyorsa doğrudan, değilse parolasız sudo ile (test sunucusunda /etc/nanobase root'ta).
readable() { [ -r "$1" ] || sudo -n test -r "$1" 2>/dev/null; }
rd() { if [ -r "$1" ]; then cat "$1"; else sudo -n cat "$1"; fi; }

say() { printf '\n== %s\n' "$*"; }

say "Mac artığı denetimi (kaynak)"
n=$(find "$SRC" -name '._*' -type f -not -path '*/node_modules/*' | wc -l)
[ "$n" -eq 0 ] || { echo "kaynakta $n adet ._* var; git archive ile yeniden al"; exit 1; }

say "İmaj: $IMAGE"
# VM'e test sunucusunda derlenmiş imaj taşınır (docker save | docker load): varsa yeniden derlenmez.
if docker image inspect "$IMAGE" >/dev/null 2>&1 && [ "${REBUILD:-0}" != 1 ]; then
  echo "imaj hazır, derleme atlandı"
else
  docker build -f "$SRC/docker/Containerfile" --build-arg "CODE_VERSION=$SHA" -t "$IMAGE" "$SRC"
fi

say "Yapılandırma: $DEST"
mkdir -p "$DEST" 2>/dev/null || { sudo -n mkdir -p "$DEST" && sudo -n chown "$(id -u):$(id -g)" "$DEST"; }
cp "$SRC/docker/compose.yaml" "$DEST/compose.yaml"
COMPOSE_FILES=(-f "$DEST/compose.yaml")
for f in $COMPOSE_EXTRA; do
  cp "$SRC/docker/$f" "$DEST/$f" && COMPOSE_FILES+=(-f "$DEST/$f")
done
if [ ! -f "$DEST/.env" ]; then
  umask 077
  printf 'DESTEK_IMAGE=%s\nSITE_NAME=%s\nHTTP_PORT=8447\nDB_ROOT_PASSWORD=%s\n' \
    "$IMAGE" "$SITE" "$(openssl rand -hex 24)" > "$DEST/.env"
fi
sed -i "s|^DESTEK_IMAGE=.*|DESTEK_IMAGE=$IMAGE|" "$DEST/.env"
set -a; . "$DEST/.env"; set +a

dc() { docker compose -p "$PROJECT" --env-file "$DEST/.env" "${COMPOSE_FILES[@]}" "$@"; }

say "Yığın"
dc up -d --remove-orphans
for _ in $(seq 60); do dc exec -T backend true 2>/dev/null && break; sleep 2; done

if dc exec -T backend test -d "sites/$SITE"; then
  say "Site var → göç"
  dc exec -T backend bench --site "$SITE" migrate
else
  say "Site yok → kurulum"
  if ! readable "$ADMIN_FILE"; then
    if [ -w "$(dirname "$ADMIN_FILE")" ]; then (umask 077; openssl rand -base64 18 > "$ADMIN_FILE")
    else openssl rand -base64 18 | sudo -n tee "$ADMIN_FILE" >/dev/null && sudo -n chmod 600 "$ADMIN_FILE"; fi
  fi
  ADMIN_PW=$(rd "$ADMIN_FILE" | tr -d '\n')
  dc exec -T backend bench new-site "$SITE" \
    --mariadb-user-host-login-scope='%' \
    --db-root-username root --db-root-password "$DB_ROOT_PASSWORD" \
    --admin-password "$ADMIN_PW" \
    --install-app helpdesk --install-app flow --install-app nanobase_brand \
    --set-default
fi

say "Site ayarları"
# Yeni sitede zamanlayıcı kapalı gelir: e-posta kuyruğu, SLA/haftalık rapor ve bilgi bankası eşitlemesi onunla çalışır.
dc exec -T backend bench --site "$SITE" enable-scheduler
dc exec -T backend bench --site "$SITE" set-config host_name "$PUBLIC_URL"
dc exec -T backend bench --site "$SITE" set-config server_script_enabled 1
for kv in $SITE_CONFIG_EXTRA; do
  dc exec -T backend bench --site "$SITE" set-config -p "${kv%%=*}" "${kv#*=}"
done
dc exec -T backend bench --site "$SITE" execute nanobase_brand.install.apply

if readable "$LLM_KEY_FILE"; then
  say "Model tanımı"
  # Anahtar dosyadan okunur, standart girişten gider: komut satırında görünmez.
  rd "$LLM_KEY_FILE" | python3 -c 'import json,sys; print(json.dumps({"base_url": sys.argv[1], "api_key": sys.stdin.read().strip()}))' "$LLM_BASE" \
    | dc exec -T backend bench --site "$SITE" execute nanobase_brand.ai.ensure_model >/dev/null
else
  echo "UYARI: $LLM_KEY_FILE yok; yapay zekâ paneli model olmadan açılır"
fi
if readable "$AD_FILE"; then
  say "AD girişi (NTLM)"
  # Portal girişinin AD dosyası + köprünün yönetici grubu/listesi; standart girişten gider.
  ADMIN_GROUP=$(rd "$BRIDGE_ENV" 2>/dev/null | sed -n 's/^TIMAS_ADMIN_GROUP=//p' | tail -1)
  ADMIN_USERS=$(rd "$BRIDGE_ENV" 2>/dev/null | sed -n 's/^TIMAS_ADMIN_USERS=//p' | tail -1)
  rd "$AD_FILE" | python3 -c 'import json,sys; d=json.load(sys.stdin); d["admin_group"]=sys.argv[1] or "Administrators"; d["admin_users"]=sys.argv[2] or "zekiai,timasai,muratsancar"; print(json.dumps(d))' \
    "$ADMIN_GROUP" "$ADMIN_USERS" \
    | dc exec -T backend bench --site "$SITE" execute nanobase_brand.ad.ensure_ldap
else
  echo "UYARI: $AD_FILE yok; AD girişi kapalı"
fi
say "Portal oturumuyla giriş (SSO anahtarı)"
# Test sunucusunda anahtar root:www-data 640 (giriş servisi www-data); VM'de giriş kapsayıcısı bağlı klasörden okur.
if ! readable "$SSO_FILE"; then
  if [ -w "$(dirname "$SSO_FILE")" ]; then (umask 077; openssl rand -hex 32 > "$SSO_FILE")
  else openssl rand -hex 32 | sudo -n tee "$SSO_FILE" >/dev/null; fi
fi
if [ -n "$SSO_GROUP" ]; then sudo -n chown "root:$SSO_GROUP" "$SSO_FILE" && sudo -n chmod 640 "$SSO_FILE"; fi
rd "$SSO_FILE" | dc exec -T backend bench --site "$SITE" execute nanobase_brand.sso.set_secret >/dev/null

say "Destek e-postası (Gmail, zeki@: gönderim + gelen kutusu)"
# SMTP ayarı köprünün yönetim ayarlarından (ALERT_SMTP_*): şifre ekrana, komut satırına ve depoya düşmez.
BRIDGE_PY=${BRIDGE_PY:-/data/nanobaseai/bi/semantic-venv/bin/python}
BRIDGE_SRC=${BRIDGE_SRC:-/data/nanobaseai/bi/frontend/backend}
if [ -n "$SMTP_FILE" ] && readable "$SMTP_FILE"; then
  rd "$SMTP_FILE" | dc exec -T backend bench --site "$SITE" execute nanobase_brand.eposta.ensure_outgoing >/dev/null \
    && echo "e-posta hesabı hazır" || echo "UYARI: e-posta hesabı ayarlanamadı (SMTP/IMAP girişi reddetti)"
elif [ -x "$BRIDGE_PY" ] && sudo -n test -f "$BRIDGE_ENV" 2>/dev/null; then
  sudo -n env PYTHONPATH="$BRIDGE_SRC" "$BRIDGE_PY" -c '
import json, os, sys
for line in open(sys.argv[1], encoding="utf-8"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1); v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"\x27": v = v[1:-1]
        os.environ.setdefault(k.strip(), v)
# Yönetim ekranındaki değer (semantic_settings) önce, yoksa ortam; köprünün ayar sırasıyla aynı.
import sqlalchemy as sa
from semantic_layer.config import SemanticSettings
with sa.create_engine(SemanticSettings.from_env().store_dsn).connect() as db:
    stored = dict(db.execute(sa.text("select key, value from semantic_settings where key like :k"), {"k": "ALERT_SMTP_%"}).all())
c = {k: stored.get("ALERT_SMTP_" + k.upper()) or os.environ.get("ALERT_SMTP_" + k.upper(), "") for k in ("host", "port", "user", "password")}
if not (c["user"] and c["password"]): sys.exit(3)
print(json.dumps(c))' "$BRIDGE_ENV" \
    | dc exec -T backend bench --site "$SITE" execute nanobase_brand.eposta.ensure_outgoing >/dev/null \
    && echo "e-posta hesabı hazır" || echo "UYARI: e-posta hesabı ayarlanamadı (köprüde ALERT_SMTP_* yok ya da SMTP/IMAP girişi reddetti)"
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
# Canlı bildirim: bildirim servisi oturumu iç web sunucusu üzerinden doğrular (Containerfile'daki socket.io ayarı).
dc exec -T frontend grep -q 'Origin http://frontend:' /etc/nginx/conf.d/frappe.conf \
  && echo "canlı bildirim ayarı: tamam" || echo "UYARI: canlı bildirim ayarı eksik (kayıt ekranları kendiliğinden yenilenmez)"
