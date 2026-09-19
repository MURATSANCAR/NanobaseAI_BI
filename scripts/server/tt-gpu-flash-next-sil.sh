#!/usr/bin/env bash
# Qwen3.8-Flash-Next'in GPU sunucusundaki (tt-gpu) bütün izlerini KALICI olarak siler. Geri dönüşü yoktur;
# model yeniden gerekirse 186 GB, 100 Mbit hattan ≈ 4,5 saatte iner.
#
# Kullanıcı çalıştırır (tt-gpu üzerinde). Canlı Flash-Next çalışıyorsa önce durdurur: o andan 27B açılana
# kadar BI köprüsü ve TİMAŞ VM modelsiz kalır.
#   bash tt-gpu-flash-next-sil.sh            # aşağıdaki "kesin Flash-Next" listesini siler
set -euo pipefail

MODEL_DIR=/data/hf-cache/hub/models--Qwen--Qwen3.8-Flash-Next-FP8
RUN_DIR=/data/qwen38

echo "== silinecekler"
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E '^(qwen38-flash-next|qwen38-download)\b' || true
sudo du -sh "$MODEL_DIR" "$RUN_DIR" 2>/dev/null || true
docker images --format '{{.Repository}}:{{.Tag}}\t{{.Size}}' | grep -E 'qwen38-flash-next' || true
read -r -p "Hepsi kalıcı silinecek. Devam? (evet yazın) " ok
[[ "$ok" == "evet" ]] || { echo "vazgeçildi"; exit 1; }

echo "== konteynerler (kayıt dosyaları konteynerle birlikte gider)"
docker rm -f qwen38-flash-next qwen38-download 2>/dev/null || true

echo "== imaj (28,8 GB)"
docker rmi vllm/vllm-openai:qwen38-flash-next || true

echo "== model dosyaları, çalıştırma dizini, derleme önbelleği, indirme kaydı"
sudo rm -rf "$MODEL_DIR" "$RUN_DIR"

echo "== kalan"
docker ps -a --format '{{.Names}}' | grep -i -E 'flash|qwen38-d' || echo "Flash-Next konteyneri yok"
docker images | grep -i flash-next || echo "Flash-Next imaj etiketi yok"
ls /data/hf-cache/hub; df -h /data | tail -1
