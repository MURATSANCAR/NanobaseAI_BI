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
LLM_BASE=${LLM_BASE:-https://portal.nanobase.ai/gpu-llm/v1}
LLM_KEY_FILE=${LLM_KEY_FILE:-/etc/nanobase/timas-vm-gpu-llm.key}
ADMIN_FILE=${ADMIN_FILE:-/etc/nanobase/destek-admin.txt}
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
  KEY=$(sudo cat "$LLM_KEY_FILE")
  python3 -c 'import json,sys; print(json.dumps({"base_url": sys.argv[1], "api_key": sys.argv[2]}))' "$LLM_BASE" "$KEY" \
    | dc exec -T backend bash -c "bench --site '$SITE' execute nanobase_brand.ai.ensure_model --kwargs \"\$(cat)\"" >/dev/null
  unset KEY
else
  echo "UYARI: $LLM_KEY_FILE yok; yapay zekâ paneli model olmadan açılır"
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
