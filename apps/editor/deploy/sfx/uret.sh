#!/bin/bash
# Havuzda bulunmayan efektleri yerelde üretir (uret.py) — GPU 0'da GEÇİCİ kap, küçük bellek payı.
#   uret.sh agirlik          ağırlıkları sabit revizyondan indirir (/data/editor/models/sfx-uretim) + sha256 + LICENSE
#   uret.sh ortam            modelin Python ortamını kurar (/data/editor/sfx/_ops/moss-venv; bir kez)
#   uret.sh uret [--esik X | --liste dosya]
# Model: OpenMOSS-Team/MOSS-SoundEffect-v2.0 (Apache-2.0), kod github.com/OpenMOSS/MOSS-TTS (Apache-2.0) sabit commit.
set -eu
HERE=$(cd "$(dirname "$0")/../.." && pwd)
REV=e35df4d82fbe87fcd5d14e5d100e349c0c3c076d
CODE_REV=${MOSS_CODE_REV:-main}
M=/data/editor/models/sfx-uretim/MOSS-SoundEffect-v2.0
case "${1:-}" in
  agirlik)
    mkdir -p "$M"
    for f in model_index.json scheduler/scheduler_config.json text_encoder/config.json text_encoder/generation_config.json \
             text_encoder/model-00001-of-00002.safetensors text_encoder/model-00002-of-00002.safetensors \
             text_encoder/model.safetensors.index.json tokenizer/merges.txt tokenizer/tokenizer.json \
             tokenizer/tokenizer_config.json tokenizer/vocab.json transformer/config.json \
             transformer/diffusion_pytorch_model.safetensors vae/config.json vae/vae_128d_48k.pth README.md; do
      mkdir -p "$M/$(dirname "$f")"
      [ -s "$M/$f" ] || wget -q -c -O "$M/$f" "https://huggingface.co/OpenMOSS-Team/MOSS-SoundEffect-v2.0/resolve/$REV/$f"
    done
    [ -s "$M/LICENSE" ] || wget -q -O "$M/LICENSE" https://www.apache.org/licenses/LICENSE-2.0.txt
    (cd "$M" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
    echo "ağırlıklar hazır: $(du -sh "$M" | cut -f1)"
    ;;
  ortam)
    exec docker run --rm --name sfx-uretim-ortam -u "$(id -u):$(id -g)" -e HOME=/tmp \
      -v /data/editor/sfx/_ops:/ops --entrypoint bash editor-voice:1 -c "
        set -e; python3 -m venv /ops/moss-venv; . /ops/moss-venv/bin/activate; pip install -q --upgrade pip
        cd /tmp && git clone -q https://github.com/OpenMOSS/MOSS-TTS.git && cd MOSS-TTS && git checkout -q $CODE_REV
        git rev-parse HEAD > /ops/moss-venv/KOD-REV
        cd moss_soundeffect_v2 && pip install -q --extra-index-url https://download.pytorch.org/whl/cu128 '.[torch-cu128]'
        python -c 'import moss_soundeffect_v2, torch; print(torch.__version__)'"
    ;;
  uret)
    shift
    # Kart: SFX_GPU (varsayılan 0). GPU 0 BI modeliyle doluysa (2026-09-28: 12 GB payda bellek yetmedi) editörün
    # kartı 1 seçilir; yalnız kartta yeterli boş bellek varken ve stüdyoda süren iş yokken çalıştırılır.
    # SFX_URETIM_CIHAZ=cpu: kartsız (yavaş ama hiçbir GPU işini etkilemez; gözetimsiz uzun koşu için).
    GPU=(--gpus "\"device=${SFX_GPU:-0}\"")
    [ "${SFX_URETIM_CIHAZ:-cuda}" = "cpu" ] && GPU=()
    exec docker run --rm --name "sfx-uretim-${SFX_URETIM_CIHAZ:-cuda}" "${GPU[@]}" -u "$(id -u):$(id -g)" -e HOME=/tmp \
      -e SFX_URETIM_CIHAZ="${SFX_URETIM_CIHAZ:-cuda}" -e SFX_THREADS="${SFX_THREADS:-32}" \
      -e SFX_URETIM_BOS_GB="${SFX_URETIM_BOS_GB:-12}" \
      -e TORCHDYNAMO_DISABLE=1 -e TQDM_DISABLE=1 -e SFX_GPU_FRACTION="${SFX_GPU_FRACTION:-0.12}" \
      -v /data/editor/sfx:/data/editor/sfx -v /data/editor/sfx/_ops:/ops -v "$M":/model/MOSS-SoundEffect-v2.0:ro \
      -v /data/editor/storage/production:/busy:ro \
      -v "$HERE":/src:ro --entrypoint bash editor-voice:1 -c '. /ops/moss-venv/bin/activate && python /src/deploy/sfx/uret.py "$@"' _ "$@"
    ;;
  *) echo "kullanım: uret.sh agirlik | ortam | uret [--esik X | --liste dosya]"; exit 2 ;;
esac
