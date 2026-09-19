#!/usr/bin/env bash
# TİMAŞ BI VM'inin (192.168.0.55) modelini harici sağlayıcıdan kendi GPU sunucumuza alır.
#
# Neden bu yol: VM, Türk Telekom'daki GPU makinesine (172.23.85.10) doğrudan ulaşamaz (TİMAŞ ile TT ağı
# arasında yol yok; 2026-09-19 ölçümü). VM internete çıkar; bu sunucu (nanobase-direct) internette, TLS'li
# (portal.nanobase.ai) ve GPU ters tüneli onda açık (127.0.0.1:18885 → GPU :8001). Köprü nginx'tir:
#   VM köprüsü ──TLS──▶ https://portal.nanobase.ai/gpu-llm/v1/ ──▶ 127.0.0.1:18885 ──SSH──▶ GPU :8001
# Koruma: 256-bit Bearer anahtarı (TLS üzerinden). IP kısıtı YOK — TİMAŞ'ın internete çıkış adresi tek
# değil, dinamik havuz (ölçümde 85.105.129.94, 85.105.155.33, 212.156.126.250 görüldü). Güvenlik modeli
# NVIDIA/OpenAI ile aynı: TLS + API anahtarı. Anahtar /etc/nanobase/timas-vm-gpu-llm.key (kullanıcı seçti).
#
# Bu sunucuda (nanobase-direct) sudo ile çalıştırılır. Yeniden çalıştırmak güvenlidir.
#   bash scripts/server/timas-vm-gpu-llm-setup.sh            # kur + VM'i çevir + doğrula
#   bash scripts/server/timas-vm-gpu-llm-setup.sh --rollback # VM'i eski ayarına döndür, ucu kapat
set -euo pipefail

VM="${VM:-timas-vm}"
VM_DIR="${VM_DIR:-/home/ai/bi-docker/infra/docker/bi}"
PUBLIC="${PUBLIC:-https://portal.nanobase.ai/gpu-llm/v1}"
UPSTREAM="${UPSTREAM:-http://127.0.0.1:18885/v1/}"
MODEL="${MODEL:-nanobaseAI}"
SITE=/etc/nginx/sites-enabled/portal.nanobase.ai   # nginx'in gerçekten okuduğu dosya (kısayol değil, ayrı kopya)
STALE=/etc/nginx/sites-available/portal.nanobase.ai
SNIPPET=/etc/nginx/snippets/timas-vm-gpu-llm.conf
KEYFILE=/etc/nanobase/timas-vm-gpu-llm.key
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"

if [[ "${1:-}" == "--rollback" ]]; then
  echo "== VM eski ayarına dönüyor"
  $SSH "$VM" "cd $VM_DIR && test -f .env.before-gpu-llm && cp .env.before-gpu-llm .env && chmod 600 .env && docker compose up -d bridge jobs && echo 'VM eski .env ile ayakta'"
  echo "== uç kapatılıyor"
  sudo sed -i '\#snippets/timas-vm-gpu-llm.conf#d' "$SITE" "$STALE" 2>/dev/null || true
  sudo nginx -t && sudo nginx -s reload
  echo "bitti (anahtar ve parça dosyası yerinde: $KEYFILE, $SNIPPET)"
  exit 0
fi

echo "== 1/5 GPU tüneli bu sunucuda cevap veriyor mu"
code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "${UPSTREAM}models")
[[ "$code" == 200 ]] || { echo "HATA: $UPSTREAM cevap vermiyor (HTTP $code). GPU ters tüneli kapalı; önce onu açın."; exit 1; }

echo "== 2/5 nginx ucu (yalnız anahtar; allow all sunucu bloğundan miras deny'i ezer)"
if ! sudo test -s "$KEYFILE"; then
  sudo install -m 600 -o root -g root /dev/null "$KEYFILE"
  openssl rand -hex 32 | sudo tee "$KEYFILE" >/dev/null
fi
KEY=$(sudo cat "$KEYFILE")
sudo tee "$SNIPPET" >/dev/null <<EOF
# scripts/server/timas-vm-gpu-llm-setup.sh tarafından yazıldı. TİMAŞ BI VM → GPU modeli (bkz. betiğin başı).
location ^~ /gpu-llm/v1/ {
    allow all;
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
# okunmayan sites-available kopyasında eski satır kaldıysa temizle
if [[ "$(readlink -f "$STALE")" != "$(readlink -f "$SITE")" ]]; then sudo sed -i '\#snippets/timas-vm-gpu-llm.conf#d' "$STALE" 2>/dev/null || true; fi
if ! sudo grep -q 'snippets/timas-vm-gpu-llm.conf' "$SITE"; then
  line=$(sudo grep -nE '^\s*location /health \{' "$SITE" | head -1 | cut -d: -f1)
  [[ -n "$line" ]] || { echo "HATA: $SITE içinde 'location /health {' bulunamadı; include'u 443 bloğuna elle ekleyin."; exit 1; }
  sudo sed -i "${line}i\\    include $SNIPPET;\\n" "$SITE"
fi
sudo nginx -t
sudo nginx -s reload
sleep 2

echo "== 3/5 uç doğrulama (sunucudan: anahtarsız 401, anahtarla 200)"
no_key=$(curl -s -m 10 -o /dev/null -w '%{http_code}' --resolve portal.nanobase.ai:443:127.0.0.1 "$PUBLIC/models")
with_key=$(curl -s -m 10 -o /dev/null -w '%{http_code}' --resolve portal.nanobase.ai:443:127.0.0.1 -H "Authorization: Bearer $KEY" "$PUBLIC/models")
echo "anahtarsız: $no_key · anahtarla: $with_key"
[[ "$no_key" == 401 && "$with_key" == 200 ]] || { echo "HATA: uç beklenen cevabı vermedi (401/200 bekleniyordu)."; exit 1; }

echo "== 4/5 VM ayarı (.env) — eski hâli .env.before-gpu-llm olarak saklanır"
printf '%s\n' "$KEY" | $SSH "$VM" "set -e; read -r K; cd $VM_DIR
  test -f .env.before-gpu-llm || cp -p .env .env.before-gpu-llm
  put(){ if grep -q \"^\$1=\" .env; then sed -i \"s#^\$1=.*#\$1=\$2#\" .env; else printf '%s=%s\n' \"\$1\" \"\$2\" >> .env; fi; }
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

echo "== 5/5 doğrulama: köprü konteynerinin içinden gerçek model çağrısı"
$SSH "$VM" "cd $VM_DIR && docker compose exec -T bridge python - <<'PY'
import json, os, urllib.request
base=os.environ['OPENAI_API_BASE'].rstrip('/'); key=os.environ.get('OPENAI_API_KEY',''); model=os.environ['LLM_MODEL_NAME']
print('adres:', base, '| model:', model)
b={'model':model,'messages':[{'role':'user','content':'1+1?'}],'max_tokens':8,'chat_template_kwargs':{'enable_thinking':False}}
r=urllib.request.Request(base+'/chat/completions', data=json.dumps(b).encode(), headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
o=json.load(urllib.request.urlopen(r, timeout=120))
print('CEVAP:', o['choices'][0]['message']['content'].strip()[:60], '| sunan model:', o.get('model'))
PY"
echo
echo "BİTTİ. Geri almak: bash scripts/server/timas-vm-gpu-llm-setup.sh --rollback"
