#!/usr/bin/env bash
# GPU modelinin sunulan adını iki tüketicide birden değiştirir: BI köprüsü (bu sunucu) ve
# TİMAŞ BI VM (192.168.0.55). Adres değişmez; yalnız model adı.
#
# nanobase-direct üzerinde sudo ile çalıştırılır. Yeniden çalıştırmak güvenlidir.
#   bash scripts/server/model-name-switch.sh                    # → nanobaseAI
#   OLD=nanobaseAI NEW=qwen3.8-flash-next bash ...              # geri
set -euo pipefail

OLD="${OLD:-qwen3.8-flash-next}"
NEW="${NEW:-nanobaseAI}"
BRIDGE_ENV=/etc/nanobase/semantic-bridge.env
VM="${VM:-timas-vm}"
VM_DIR="${VM_DIR:-/home/ai/bi-docker/infra/docker/bi}"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"

echo "== 1/3 model bu adla cevap veriyor mu"
curl -fsS -m 10 http://127.0.0.1:18885/v1/models | grep -q "\"id\":\"$NEW\"" \
  || { echo "HATA: 127.0.0.1:18885 '$NEW' adını sunmuyor; önce GPU'daki modeli açın."; exit 1; }

echo "== 2/3 BI köprüsü ($BRIDGE_ENV)"
sudo sed -i -E "s/^(LLM_MODEL_NAME|SEMANTIC_SELECTOR_MODEL)=$OLD\$/\1=$NEW/" "$BRIDGE_ENV"
sudo grep -n -E '^(LLM_MODEL_NAME|SEMANTIC_SELECTOR_MODEL)=' "$BRIDGE_ENV"
sudo systemctl restart nanobase-semantic-bridge
systemctl is-active nanobase-semantic-bridge

echo "== 3/3 TİMAŞ VM ($VM)"
$SSH "$VM" "cd $VM_DIR && sed -i -E 's/^(LLM_MODEL_NAME|SEMANTIC_SELECTOR_MODEL)=$OLD\$/\1=$NEW/' .env \
  && grep -n -E '^(LLM_MODEL_NAME|SEMANTIC_SELECTOR_MODEL)=' .env && docker compose up -d bridge jobs \
  && docker compose ps --format '{{.Service}} {{.Status}}'"

echo "bitti: $OLD → $NEW"
