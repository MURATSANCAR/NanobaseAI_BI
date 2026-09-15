#!/usr/bin/env bash
# ZEKİ AI — müşteri VM'ine (192.168.0.55) Docker yığınını kurar/günceller.
# Bizim sunucudan (nanobase-direct) çalıştırılır; VM'e VPN (tun0) üzerinden SSH anahtarıyla bağlanır.
#
# Önkoşullar (bir kez, müşteri tarafında):
#   1) Bizim sunucunun ~/.ssh/zeki_customer_vm.pub anahtarı ai@192.168.0.55:~/.ssh/authorized_keys içinde olmalı.
#   2) ai kullanıcısı docker grubunda olmalı:  sudo usermod -aG docker ai   (sonra yeniden giriş)
#   3) VM'de /home/ai/bi-docker/infra/docker/bi/.env (PORTAL_ORIGIN dahil), secrets/logo-mssql-connection.json
#      ve secrets/ad/timas-ad.json hazır olmalı (bu betik onlara dokunmaz).
#   4) Dış kapı HTTPS: npm-custom-http.conf başındaki adımlar (kendinden imzalı sertifika + NPM özel ayarı).
#
# Kullanım (bizim sunucuda, repo kopyasının kökünde):  bash scripts/server/deploy-customer-vm.sh
set -euo pipefail

# timas-vm: bizim sunucunun ~/.ssh/config kaydı (192.168.0.55, kullanıcı ai, anahtar ~/.ssh/zeki_customer_vm)
VM="${VM:-timas-vm}"
DST="${DST:-/home/ai/bi-docker}"
SRC="${SRC:-$(pwd)}"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=10"

echo "== erişim"; $SSH "$VM" 'id -nG | tr " " "\n" | grep -qx docker || { echo "ai docker grubunda değil"; exit 1; }; docker compose version >/dev/null'

echo "== kod gönderiliyor ($SRC → $VM:$DST)"
$SSH "$VM" "mkdir -p $DST/scripts/server/portal-login $DST/infra/docker/bi"
rsync -rc -e "$SSH" "$SRC"/{package.json,package-lock.json,index.html,tsconfig.json,tsconfig.node.json,vite.config.ts,tailwind.config.js,postcss.config.js} "$VM:$DST/"
rsync -rc --delete -e "$SSH" --exclude node_modules "$SRC/src/" "$VM:$DST/src/"
rsync -rc --delete -e "$SSH" --exclude __pycache__ --exclude '*.pyc' --exclude .venv "$SRC/backend/" "$VM:$DST/backend/"
rsync -rc --delete -e "$SSH" --exclude __pycache__ "$SRC/configs/" "$VM:$DST/configs/"
rsync -c -e "$SSH" "$SRC/scripts/server/timas-metrics-build.py" "$VM:$DST/scripts/server/"
rsync -c -e "$SSH" "$SRC"/scripts/server/portal-login/{server.py,requirements.txt} "$VM:$DST/scripts/server/portal-login/"
# .env, secrets/ ve sunucuya özel override dosyası müşteride kalır, üzerine yazılmaz.
rsync -rc -e "$SSH" --exclude .env --exclude 'secrets/' --exclude docker-compose.override.yml --exclude catalog.sql \
  "$SRC/infra/docker/bi/" "$VM:$DST/infra/docker/bi/"

echo "== derle ve kaldır"
$SSH "$VM" "cd $DST/infra/docker/bi && grep -q '^SEMANTIC_ADMIN_TOKEN=.' .env || echo 'UYARI: .env içinde SEMANTIC_ADMIN_TOKEN boş; onay kararları 403 döner'
  grep -q '^PORTAL_ORIGIN=https://' .env || { echo 'HATA: .env içinde PORTAL_ORIGIN=https://... yok; giriş 403 döner'; exit 1; }
  test -s secrets/ad/timas-ad.json || { echo 'HATA: secrets/ad/timas-ad.json yok; giriş 503 döner'; exit 1; }
  docker compose build bridge web login && docker compose up -d && sleep 60 && docker compose ps --format '{{.Service}} {{.State}} {{.Status}}'
  docker compose exec -T web nginx -t
  # Oturumsuz: sayfa 200, veri yolları 401, giriş servisi oturum sorusuna 401.
  for p in / /timas/ /timas/auth/session /timas/api/v1/engine /timas/api/v1/alerts /timas/metrics/cfo.json; do echo \"\$p -> \$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8088\$p)\"; done
  docker compose logs --tail 4 jobs"
echo "== bitti. Dış kapı: https://192.168.0.55/timas/ (NPM özel ayarı, npm-custom-http.conf)."
