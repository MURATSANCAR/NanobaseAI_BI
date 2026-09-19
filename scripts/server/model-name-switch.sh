#!/usr/bin/env bash
# GPU modelinin sunulan adını üç tüketicide birden değiştirir: BI köprüsü (bu sunucu), Editör (bu sunucu),
# TİMAŞ BI VM (192.168.0.55). Adres değişmez; yalnız model adı.
#
# nanobase-direct üzerinde sudo ile çalıştırılır. Yeniden çalıştırmak güvenlidir.
#   bash scripts/server/model-name-switch.sh                    # → nanobaseAI
#   OLD=nanobaseAI NEW=qwen3.8-flash-next bash ...              # geri
set -euo pipefail

OLD="${OLD:-qwen3.8-flash-next}"
NEW="${NEW:-nanobaseAI}"
BRIDGE_ENV=/etc/nanobase/semantic-bridge.env
EDITOR_DIR=/data/nanobaseai/editor
EDITOR_FILES="-f compose.yaml -f compose.models.yaml -f compose.ocr.yaml -f compose.reread.yaml -f compose.gpu.yaml"
VM="${VM:-timas-vm}"
VM_DIR="${VM_DIR:-/home/ai/bi-docker/infra/docker/bi}"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"

echo "== 1/4 model bu adla cevap veriyor mu"
curl -fsS -m 10 http://127.0.0.1:18885/v1/models | grep -q "\"id\":\"$NEW\"" \
  || { echo "HATA: 127.0.0.1:18885 '$NEW' adını sunmuyor; önce GPU'daki modeli açın."; exit 1; }

echo "== 2/4 BI köprüsü ($BRIDGE_ENV)"
sudo sed -i -E "s/^(LLM_MODEL_NAME|SEMANTIC_SELECTOR_MODEL)=$OLD\$/\1=$NEW/" "$BRIDGE_ENV"
sudo grep -n -E '^(LLM_MODEL_NAME|SEMANTIC_SELECTOR_MODEL)=' "$BRIDGE_ENV"
sudo systemctl restart nanobase-semantic-bridge
systemctl is-active nanobase-semantic-bridge

echo "== 3/4 Editör (yalnız modeli okuyan api ve worker yeniden kurulur)"
cd "$EDITOR_DIR"
sudo sed -i -E "s/^EDITOR_MODEL_NAME=$OLD\$/EDITOR_MODEL_NAME=$NEW/" .env
grep -n '^EDITOR_MODEL_NAME=' .env
docker compose $EDITOR_FILES up -d --no-deps api worker
for c in nanobase-editor-api-1 nanobase-editor-worker-1; do
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$c" | grep '^EDITOR_MODEL_NAME='
done

echo "== 4/4 TİMAŞ VM ($VM)"
$SSH "$VM" "cd $VM_DIR && sed -i -E 's/^(LLM_MODEL_NAME|SEMANTIC_SELECTOR_MODEL)=$OLD\$/\1=$NEW/' .env \
  && grep -n -E '^(LLM_MODEL_NAME|SEMANTIC_SELECTOR_MODEL)=' .env && docker compose up -d bridge jobs \
  && docker compose ps --format '{{.Service}} {{.Status}}'"

echo "bitti: $OLD → $NEW"
