#!/bin/bash
# havuz.py'yi GEÇİCİ kapta çalıştırır (çalışan kaplara dokunmaz; iş bitince kap silinir).
#   calistir.sh <adım> [...]      adımlar: ac | katalog [kaynak…] | gomme | metin | rapor
# Kod: bu betiğin iki üst klasörü (apps/editor) salt okunur bağlanır. Havuz /data/editor/sfx, model
# /data/editor/models/sfx-clap. `gomme` GPU 0'da küçük bellek payıyla (SFX_GPU_FRACTION, varsayılan %5) koşar;
# SFX_DEVICE=cpu ile işlemcide. Dosyalar kullanıcının kimliğiyle yazılır (root sahipli dosya bırakılmaz).
set -eu
HERE=$(cd "$(dirname "$0")/../.." && pwd)
IMAGE=${SFX_IMAGE:-editor-voice:1}
DEV=${SFX_DEVICE:-cuda}
GPU=()
[ "$DEV" = "cuda" ] && GPU=(--gpus '"device=0"')
exec docker run --rm --name "sfx-havuz-$1" "${GPU[@]}" -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
  -e SFX_DEVICE="$DEV" -e SFX_WORKERS="${SFX_WORKERS:-48}" -e SFX_THREADS="${SFX_THREADS:-8}" \
  -e SFX_BATCH="${SFX_BATCH:-64}" -e SFX_GPU_FRACTION="${SFX_GPU_FRACTION:-0.05}" \
  -v /data/editor/sfx:/data/editor/sfx -v /data/editor/models/sfx-clap:/model:ro -v "$HERE":/src:ro \
  --entrypoint bash "$IMAGE" -c 'pip install -q --user pyloudnorm==0.1.1 onnx==1.20.0 onnxruntime==1.23.2 >/dev/null 2>&1 || pip install -q --user pyloudnorm onnx onnxruntime >/dev/null 2>&1; cd /tmp && python3 /src/deploy/sfx/havuz.py "$@"' _ "$@"
