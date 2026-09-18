#!/usr/bin/env bash
# TİMAŞ BI VM'inin (192.168.0.55) modelini harici sağlayıcıdan GPU sunucusuna alır.
#
# Neden bu yol: VM, Türk Telekom ağındaki GPU makinesine (172.23.85.10) doğrudan ulaşamaz — TİMAŞ ile TT
# arasında yol yok (2026-09-19 ölçümü: VM'den :8001 kapalı; :80/:443 TCP'yi TİMAŞ güvenlik duvarının vekili
# kabul ediyor ama arkasından HTTP cevabı, sertifika ya da /v1/models gelmiyor). VM internete çıkabiliyor
# (çıkış IP'si 85.105.129.94); bu sunucu (nanobase-direct) internette, TLS'li (portal.nanobase.ai) ve GPU ters
# tüneli onda açık (127.0.0.1:18885 → GPU :8001, editor-gpu-tunnel). Köprü noktası bu sunucunun nginx'idir:
#
#   VM köprüsü ──TLS──▶ https://portal.nanobase.ai/gpu-llm/v1/  (yalnız TİMAŞ çıkış IP'si + anahtar)
#                        └─▶ 127.0.0.1:18885 ──SSH ters tünel──▶ GPU :8001 (qwen3.8-flash-next)
#
# Bu sunucuda (nanobase-direct), sudo yetkisiyle çalıştırılır. Yeniden çalıştırmak güvenlidir.
#   bash scripts/server/timas-vm-gpu-llm-setup.sh            # kur + VM'i çevir + doğrula
#   bash scripts/server/timas-vm-gpu-llm-setup.sh --rollback # VM'i eski ayarına döndür, ucu kapat
set -euo pipefail

VM="${VM:-timas-vm}"
VM_DIR="${VM_DIR:-/home/ai/bi-docker/infra/docker/bi}"
ALLOW_IP="${ALLOW_IP:-85.105.129.94}"          # TİMAŞ'ın internete çıkış adresi (VM'de: curl https://api.ipify.org)
PUBLIC="${PUBLIC:-https://portal.nanobase.ai/gpu-llm/v1}"
UPSTREAM="${UPSTREAM:-http://127.0.0.1:18885/v1/}"
MODEL="${MODEL:-qwen3.8-flash-next}"
# nginx'in gerçekten okuduğu dosya. Bu sunucuda sites-enabled bir kısayol değil, ayrı bir kopya: sites-available'a
# yazılan satır yüklenmez (2026-09-19, ilk denemede 404).
SITE=/etc/nginx/sites-enabled/portal.nanobase.ai
STALE=/etc/nginx/sites-available/portal.nanobase.ai
SNIPPET=/etc/nginx/snippets/timas-vm-gpu-llm.conf
KEYFILE=/etc/nanobase/timas-vm-gpu-llm.key
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"

if [[ "${1:-}" == "--rollback" ]]; then
  echo "== VM eski ayarına dönüyor"
  $SSH "$VM" "cd $VM_DIR && test -f .env.before-gpu-llm && cp .env.before-gpu-llm .env && docker compose up -d bridge jobs && echo 'VM eski .env ile ayakta'"
  echo "== uç kapatılıyor"
  sudo sed -i '\#snippets/timas-vm-gpu-llm.conf#d' "$SITE" "$STALE"
  sudo nginx -t && sudo nginx -s reload
  echo "bitti (anahtar ve parça dosyası yerinde bırakıldı: $KEYFILE, $SNIPPET)"
  exit 0
fi

echo "== 1/5 GPU tüneli bu sunucuda cevap veriyor mu"
code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "${UPSTREAM}models")
[[ "$code" == 200 ]] || { echo "HATA: $UPSTREAM cevap vermiyor (HTTP $code). GPU ters tüneli kapalı; önce onu açın."; exit 1; }

echo "== 2/5 nginx ucu (yalnız $ALLOW_IP + anahtar)"
if ! sudo test -s "$KEYFILE"; then
  sudo install -m 600 -o root -g root /dev/null "$KEYFILE"
  openssl rand -hex 32 | sudo tee "$KEYFILE" >/dev/null
fi
KEY=$(sudo cat "$KEYFILE")
sudo tee "$SNIPPET" >/dev/null <<EOF
# scripts/server/timas-vm-gpu-llm-setup.sh tarafından yazıldı. TİMAŞ BI VM → GPU modeli (bkz. betiğin başı).
location ^~ /gpu-llm/v1/ {
    allow $ALLOW_IP;
    deny all;
    if (\$http_authorization != "Bearer $KEY") { return 401; }
    proxy_pass $UPSTREAM;
    proxy_http_version 1.1;
    proxy_set_header Host 127.0.0.1;
    proxy_set_header Authorization "";
    proxy_buffering off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
    client_max_body_size 32m;
    access_log /var/log/nginx/timas-vm-gpu-llm.access.log;
}
EOF
sudo chmod 600 "$SNIPPET"
if [[ "$(readlink -f "$STALE")" != "$(readlink -f "$SITE")" ]]; then sudo sed -i '\#snippets/timas-vm-gpu-llm.conf#{N;d}' "$STALE" 2>/dev/null || true; fi
if ! sudo grep -q 'snippets/timas-vm-gpu-llm.conf' "$SITE"; then
  line=$(sudo grep -nE '^\s*location /health \{' "$SITE" | head -1 | cut -d: -f1)
  [[ -n "$line" ]] || { echo "HATA: $SITE içinde 'location /health {' bulunamadı; include satırını 443 sunucu bloğuna elle ekleyin."; exit 1; }
  sudo sed -i "${line}i\\    include $SNIPPET;\\n" "$SITE"
fi
sudo nginx -t
sudo nginx -s reload
sleep 2
loaded=$(sudo nginx -T 2>/dev/null | grep -c 'location ^~ /gpu-llm/v1/' || true)
[[ "$loaded" -ge 1 ]] || { echo "HATA: nginx yeni ucu yüklemedi (nginx -T içinde yok)."; exit 1; }
local_code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' --resolve portal.nanobase.ai:443:127.0.0.1 "$PUBLIC/models")
# nginx'te "if … return" (rewrite evresi) IP denetiminden (access evresi) önce çalışır: anahtarsız istek 401 alır.
[[ "$local_code" == 401 ]] || { echo "HATA: uç sunucunun kendisine $local_code döndü (401 beklenirdi: anahtar yok)."; exit 1; }

echo "== 3/5 uç, VM'den deneniyor (anahtarsız 401, anahtarla 200 beklenir)"
no_key=$($SSH "$VM" "curl -s -m 15 -o /dev/null -w '%{http_code}' $PUBLIC/models")
with_key=$(printf '%s' "$KEY" | $SSH "$VM" "read -r K; curl -s -m 15 -o /dev/null -w '%{http_code}' -H \"Authorization: Bearer \$K\" $PUBLIC/models")
echo "anahtarsız: $no_key · anahtarla: $with_key"
[[ "$no_key" == 401 && "$with_key" == 200 ]] || {
  echo "HATA: uç beklenen cevabı vermedi. 403 ise VM'in çıkış IP'si $ALLOW_IP değildir (VM'de: curl https://api.ipify.org) — ALLOW_IP=… ile yeniden çalıştırın."; exit 1; }

echo "== 4/5 VM ayarı (.env) — eski hâli .env.before-gpu-llm olarak saklanır"
printf '%s' "$KEY" | $SSH "$VM" "set -e; read -r K; cd $VM_DIR
  test -f .env.before-gpu-llm || cp .env .env.before-gpu-llm
  put() { if grep -q \"^\$1=\" .env; then sed -i \"s#^\$1=.*#\$1=\$2#\" .env; else printf '%s=%s\n' \"\$1\" \"\$2\" >> .env; fi; }
  put OPENAI_API_BASE '$PUBLIC'
  put SEMANTIC_SELECTOR_BASE '$PUBLIC'
  put LLM_MODEL_NAME '$MODEL'
  put SEMANTIC_SELECTOR_MODEL '$MODEL'
  put OPENAI_API_KEY \"\$K\"
  put LLM_EXTRA_BODY_JSON '{\"chat_template_kwargs\":{\"enable_thinking\":false}}'
  chmod 600 .env
  docker compose up -d bridge jobs
  sleep 25
  docker compose ps --format '{{.Service}} {{.State}} {{.Status}}'"

echo "== 5/5 doğrulama: köprü konteynerinin içinden gerçek bir model çağrısı"
$SSH "$VM" "cd $VM_DIR && docker compose exec -T bridge python - <<'PY'
import json, os, urllib.request
base, key, model = os.environ['OPENAI_API_BASE'].rstrip('/'), os.environ.get('OPENAI_API_KEY', ''), os.environ['LLM_MODEL_NAME']
print('köprünün model adresi:', base, '| model:', model)
body = {'model': model, 'messages': [{'role': 'user', 'content': '1+1?'}], 'max_tokens': 8, 'chat_template_kwargs': {'enable_thinking': False}}
req = urllib.request.Request(base + '/chat/completions', data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
out = json.load(urllib.request.urlopen(req, timeout=120))
print('cevap:', out['choices'][0]['message']['content'].strip()[:60], '| sunan model:', out.get('model'))
PY"
echo
echo "BİTTİ. Yönetim ekranında (Yönetim → Yapay zekâ modeli) daha önce bir model adresi KAYDEDİLMİŞSE o değer .env'i ezer:"
echo "ekranda adresin $PUBLIC göründüğünü kontrol edin, gerekirse oradan kaydedin ve 'Bağlantıyı dene'yi çalıştırın."
echo "Geri almak: bash scripts/server/timas-vm-gpu-llm-setup.sh --rollback"
