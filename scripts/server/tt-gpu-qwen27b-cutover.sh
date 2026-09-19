#!/usr/bin/env bash
# GPU sunucusundaki (tt-gpu) ana modeli Qwen3.8-Flash-Next-FP8'den Qwen3.8-27B-FP8'e çevirir.
#
# Neden: Flash-Next 186 GB; iki H100 NVL'in toplamı 188 GB. Resmî tarif 4 kart ister; biz n-gram tablosunu
# RAM'e atarak sınırda çalışıyorduk (OCR ile bellek taşması, soğuk açılışta 64 → 88 GiB sıçraması).
# 27B-FP8 ≈ 28 GB: iki karta bölünür (kart başına ≈ 14 GB), kalan bellek tek KV havuzu olur.
#
# tt-gpu üzerinde çalıştırılır (TT VPN açıkken `ssh tt-gpu`). Yeniden çalıştırmak güvenlidir.
#   bash tt-gpu-qwen27b-cutover.sh --download   # yalnız indir; canlı model çalışmaya devam eder
#   bash tt-gpu-qwen27b-cutover.sh              # indir (eksikse) + Flash-Next'i durdur + 27B'yi aç + dene
#   bash tt-gpu-qwen27b-cutover.sh --rollback   # 27B'yi durdur, Flash-Next'i yeniden aç
#
# Bu betik HİÇBİR ŞEY SİLMEZ. Flash-Next yalnız durdurulur; geri dönüş yolu açık kalır.
# Silme ayrı ve elle yapılır: betiğin sonunda basılan komutlar, 27B kabul edildikten sonra.
set -euo pipefail

REPO="Qwen/Qwen3.8-27B-FP8"
NAME="nanobaseAI"
CACHE="${CACHE:-/data/hf-cache}"
NEW_DIR="${NEW_DIR:-/data/qwen27}"
OLD_DIR="${OLD_DIR:-/data/qwen38}"
PORT="${PORT:-8001}"
# İmaj makinede hazır olmalı (OCR servisi 0.27.1 kullanıyor). Başka etiket için: QWEN27_IMAGE=... bash ...
export QWEN27_IMAGE="${QWEN27_IMAGE:-vllm/vllm-openai:v0.27.1}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

wait_health() {   # $1 = en çok kaç saniye
  local until=$(( $(date +%s) + $1 ))
  while (( $(date +%s) < until )); do
    curl -fsS -m 5 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && return 0
    sleep 10
  done
  return 1
}

if [[ "${1:-}" == "--rollback" ]]; then
  echo "== 27B durduruluyor, Flash-Next açılıyor"
  docker compose -f "$NEW_DIR/docker-compose.yml" stop || true
  docker compose -f "$OLD_DIR/docker-compose.yml" up -d
  wait_health 2400 && echo "Flash-Next ayakta ($PORT)" || { echo "HATA: Flash-Next 40 dk içinde açılmadı"; exit 1; }
  exit 0
fi

echo "== 1/5 ön denetim"
docker image inspect "$QWEN27_IMAGE" >/dev/null 2>&1 || { echo "HATA: imaj yok: $QWEN27_IMAGE (docker images | grep vllm)"; exit 1; }
free_gb=$(df -BG --output=avail "$CACHE" | tail -1 | tr -dc 0-9)
(( free_gb > 60 )) || { echo "HATA: $CACHE altında $free_gb GB boş; en az 60 GB gerekir"; exit 1; }
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader

echo "== 2/5 indirme → $CACHE (xet kapalı: bu hatta takılıyor; düz HTTP ≈ 11 MB/sn, ≈ 40 dk)"
docker run --rm --name qwen27-download --entrypoint python3 \
  -e HF_HUB_DISABLE_XET=1 -v "$CACHE:/root/.cache/huggingface" "$QWEN27_IMAGE" -c "
from huggingface_hub import snapshot_download, HfApi
path = snapshot_download('$REPO')
import os
want = {s.rfilename: s.size for s in HfApi().model_info('$REPO', files_metadata=True).siblings}
bad = [f for f, size in want.items() if size is not None and os.path.getsize(os.path.join(path, f)) != size]
print('dosya', len(want), 'boyutu tutmayan', len(bad), bad[:5])
raise SystemExit(1 if bad else 0)
"
[[ "${1:-}" == "--download" ]] && { echo "indirme tamam; canlı modele dokunulmadı"; exit 0; }

echo "== 3/5 çalıştırma dosyası → $NEW_DIR"
sudo install -d -o "$USER" "$NEW_DIR"
install -m 644 "$HERE/compose.qwen27b.yaml" "$NEW_DIR/docker-compose.yml"
docker compose -f "$NEW_DIR/docker-compose.yml" config -q

echo "== 4/5 Flash-Next durduruluyor (silinmiyor; silme: tt-gpu-flash-next-sil.sh), 27B açılıyor"
if [[ -f "$OLD_DIR/docker-compose.yml" ]]; then docker compose -f "$OLD_DIR/docker-compose.yml" stop; else echo "(Flash-Next zaten silinmiş)"; fi
docker compose -f "$NEW_DIR/docker-compose.yml" up -d
if ! wait_health 900; then
  echo "HATA: 27B 15 dk içinde açılmadı. Son kayıtlar:"
  docker logs --tail 40 qwen38-27b || true
  echo "Geri dönüş: bash $0 --rollback"
  exit 1
fi

echo "== 5/5 deneme"
curl -fsS -m 10 "http://127.0.0.1:$PORT/v1/models" | head -c 300; echo
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
echo "-- düşünme kapalı, kısa Türkçe cevap"
curl -fsS -m 120 "http://127.0.0.1:$PORT/v1/chat/completions" -H 'Content-Type: application/json' -d "{
  \"model\":\"$NAME\",\"temperature\":0,\"max_tokens\":60,
  \"chat_template_kwargs\":{\"enable_thinking\":false},
  \"messages\":[{\"role\":\"user\",\"content\":\"Tek cümleyle: KDV nedir?\"}]}" | head -c 600; echo
echo "-- kapalı küme + olasılık (Editörün kullandığı yol)"
curl -fsS -m 120 "http://127.0.0.1:$PORT/v1/chat/completions" -H 'Content-Type: application/json' -d "{
  \"model\":\"$NAME\",\"temperature\":0,\"max_tokens\":1,\"logprobs\":true,\"top_logprobs\":3,
  \"chat_template_kwargs\":{\"enable_thinking\":false},
  \"structured_outputs\":{\"choice\":[\"A\",\"B\",\"C\"]},
  \"messages\":[{\"role\":\"user\",\"content\":\"Türkiye'nin başkenti? A) İzmir B) Ankara C) Bursa. Yalnız harf.\"}]}" | head -c 900; echo

cat <<EOF

27B ayakta: port $PORT, model adı $NAME. Tüketicilerde model adı değişmeli (LLM_MODEL_NAME / EDITOR_MODEL_NAME).
Flash-Next DURDURULDU, SİLİNMEDİ. Geri dönüş: bash $0 --rollback

27B kabul edildikten sonra Flash-Next'i silmek için (elle, geri dönüşü yok — önce ne silineceğine bakın):
  docker ps -a --filter name=qwen38 ; docker images | grep -i flash-next ; du -sh $CACHE/hub/models--Qwen--Qwen3.8-Flash-Next-FP8 $OLD_DIR
  docker compose -f $OLD_DIR/docker-compose.yml down
  docker rm -f qwen38-download 2>/dev/null
  docker rmi vllm/vllm-openai:qwen38-flash-next
  sudo rm -rf $CACHE/hub/models--Qwen--Qwen3.8-Flash-Next-FP8 $OLD_DIR
EOF
