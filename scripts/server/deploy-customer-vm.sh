#!/usr/bin/env bash
# ZEKİ AI — müşteri VM'ine (192.168.0.55) Docker yığınını kurar/günceller.
# Bizim sunucudan (nanobase-direct) çalıştırılır; VM'e VPN (tun0) üzerinden SSH anahtarıyla bağlanır.
#
# Önkoşullar (bir kez, müşteri tarafında):
#   1) Bizim sunucunun ~/.ssh/zeki_customer_vm.pub anahtarı ai@192.168.0.55:~/.ssh/authorized_keys içinde olmalı.
#   2) ai kullanıcısı docker grubunda olmalı:  sudo usermod -aG docker ai   (sonra yeniden giriş)
#   3) VM'de /home/ai/bi-docker/infra/docker/bi/.env (PORTAL_ORIGIN dahil), secrets/logo-mssql-connection.json,
#      secrets/crm-mssql-connection.json (canlı CRM) ve secrets/ad/timas-ad.json hazır olmalı (bu betik onlara dokunmaz).
#   4) Dış kapı: npm-custom-http.conf (NPM özel ayarı, HTTP).
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
rsync -rc --exclude "._*" -e "$SSH" "$SRC"/{package.json,package-lock.json,index.html,tsconfig.json,tsconfig.node.json,vite.config.ts,tailwind.config.js,postcss.config.js} "$VM:$DST/"
rsync -rc --delete --exclude "._*" -e "$SSH" --exclude node_modules "$SRC/src/" "$VM:$DST/src/"
rsync -rc --delete --exclude "._*" -e "$SSH" --exclude __pycache__ --exclude '*.pyc' --exclude .venv "$SRC/backend/" "$VM:$DST/backend/"
rsync -rc --delete --exclude "._*" -e "$SSH" --exclude __pycache__ "$SRC/configs/" "$VM:$DST/configs/"
rsync -c --exclude "._*" -e "$SSH" "$SRC/scripts/server/timas-metrics-build.py" "$VM:$DST/scripts/server/"
# İş çalıştırıcının takvimi: test sunucusundaki zamanlayıcıların aynısı (infra/docker/bi/jobs.py okur).
rsync -c --exclude "._*" -e "$SSH" "$SRC"/scripts/server/timas-*.timer "$SRC"/scripts/server/timas-*.service "$VM:$DST/scripts/server/"
rsync -c --exclude "._*" -e "$SSH" "$SRC"/scripts/server/portal-login/{server.py,requirements.txt} "$VM:$DST/scripts/server/portal-login/"
# .env, secrets/ ve sunucuya özel override dosyası müşteride kalır, üzerine yazılmaz.
rsync -rc --exclude "._*" -e "$SSH" --exclude .env --exclude 'secrets/' --exclude docker-compose.override.yml --exclude catalog.sql \
  "$SRC/infra/docker/bi/" "$VM:$DST/infra/docker/bi/"

echo "== derle ve kaldır"
$SSH "$VM" "cd $DST/infra/docker/bi && grep -q '^SEMANTIC_ADMIN_TOKEN=.' .env || echo 'UYARI: .env içinde SEMANTIC_ADMIN_TOKEN boş; onay kararları 403 döner'
  grep -q '^PORTAL_ORIGIN=http' .env || { echo 'HATA: .env içinde PORTAL_ORIGIN yok; giriş 403 döner'; exit 1; }
  test -s secrets/ad/timas-ad.json || { echo 'HATA: secrets/ad/timas-ad.json yok; giriş 503 döner'; exit 1; }
  test -s secrets/crm-mssql-connection.json || { echo 'HATA: secrets/crm-mssql-connection.json yok; CRM ekranları Logo sunucusuna düşer'; exit 1; }
  docker compose build bridge web login
  # Kurulum müşteri verisini silmez (kullanıcı kuralı 2026-09-25). bi_var ilk kez oluşturuluyorsa çalışan köprünün
  # konteyner katmanındaki durum (rapor önbelleği, Finansal Denetim arşivi, editör verisi) önce bu diske kopyalanır.
  if ! docker volume inspect bi_var >/dev/null 2>&1; then
    docker volume create bi_var >/dev/null
    if docker inspect bi-bridge-1 >/dev/null 2>&1; then
      rm -rf /tmp/bi-var-seed && docker cp bi-bridge-1:/data/nanobaseai/bi/var /tmp/bi-var-seed 2>/dev/null || mkdir -p /tmp/bi-var-seed
      docker run --rm --entrypoint sh -v bi_var:/v -v /tmp/bi-var-seed:/src:ro nanobase-bi-bridge:latest -c 'cp -a /src/. /v/ && find /v -type f | wc -l' | sed 's/^/bi_var: taşınan dosya /'
      rm -rf /tmp/bi-var-seed
    fi
  fi
  before=\$(docker exec bi-bridge-1 sh -c 'ls /data/nanobaseai/bi/var/management-reports 2>/dev/null | wc -l' 2>/dev/null || echo 0)
  docker compose up -d && sleep 60 && docker compose ps --format '{{.Service}} {{.State}} {{.Status}}'
  after=\$(docker exec bi-bridge-1 sh -c 'ls /data/nanobaseai/bi/var/management-reports 2>/dev/null | wc -l')
  echo \"bi_var korundu: rapor önbelleği dosya \$before → \$after\"
  docker compose exec -T web nginx -t
  # Oturumsuz: sayfa 200, veri yolları 401, giriş servisi oturum sorusuna 401.
  for p in / /timas/ /timas/auth/session /timas/api/v1/engine /timas/api/v1/alerts /timas/metrics/cfo.json; do echo \"\$p -> \$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8088\$p)\"; done
  docker compose logs --tail 4 jobs"
# M48 sürüm kaydı: kurulan main sürümü, köprü imajı ve VM'deki Mac artığı sayısı hem test sunucusunun köprüsüne (ortam
# eşliği orada görünür) hem VM'in kendi köprüsüne yazılır. Kaynak git archive olduğu için sürüm CODE_SHA ile verilir
# (örn. CODE_SHA=$(git rev-parse main)); verilmezse SRC/.code-sha okunur.
echo "== sürüm kaydı"
AD_VM="$($SSH "$VM" "find $DST -name '._*' -type f -not -path '*/node_modules/*' | wc -l" | tr -d ' ')"
IMG_VM="$($SSH "$VM" "docker inspect bi-bridge-1 --format '{{.Config.Image}}'" 2>/dev/null || true)"
SHA="${CODE_SHA:-$(cat "$SRC/.code-sha" 2>/dev/null || git -C "$SRC" rev-parse HEAD 2>/dev/null || echo bilinmiyor)}"
if [[ -r /etc/nanobase/semantic-bridge.env ]]; then set +u -a; . /etc/nanobase/semantic-bridge.env; set -u +a; fi
ENV=vm APPLEDOUBLE="${AD_VM:-0}" IMAGE="$IMG_VM" CODE_SHA="$SHA" ROOT="$SRC" bash "$SRC/scripts/server/itops-report-release.sh" || true
printf '{"env":"vm","codeSha":"%s","image":"%s","appledoubleCount":%s,"reportedBy":"kurulum:deploy-customer-vm"}' \
  "$SHA" "$IMG_VM" "${AD_VM:-0}" | $SSH "$VM" "docker exec -i bi-bridge-1 python3 -c 'import os,sys,urllib.request as u; r=u.Request(\"http://127.0.0.1:8795/api/v1/it-ops/report-release\", data=sys.stdin.buffer.read(), method=\"POST\", headers={\"Content-Type\": \"application/json\", \"X-Semantic-Caller\": os.environ.get(\"SEMANTIC_CALLER_TOKEN\", \"\")}); print(u.urlopen(r, timeout=20).read().decode()[:300])'" \
  || echo "UYARI: sürüm kaydı VM köprüsüne yazılamadı"
echo "== bitti. Dış kapı: http://192.168.0.55/timas/ (NPM özel ayarı, npm-custom-http.conf)."
