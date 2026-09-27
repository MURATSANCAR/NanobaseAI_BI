#!/bin/bash
# Havuzu bitirir: süren indirmeler (Sonniss aynası yavaş, FSD50K eval, Commons) bitince açar, kataloğa yazar, gömer
# ve kapsama ölçümünü yeniden koşar. Her adım artımlıdır (önceden işlenen dosya yeniden işlenmez). GPU'da arka planda:
#   setsid nohup kod/deploy/sfx/tamamla.sh > tamamla.log 2>&1 &
# Gömme işlemcide (SFX_DEVICE=cpu): gözetimsiz koşuda GPU 0'ın boş belleğine güvenilmez.
set -u
OPS=/data/editor/sfx/_ops
K=$(cd "$(dirname "$0")" && pwd)
bitti() { grep -q "BITTI" "$OPS/$1.log" 2>/dev/null; }
until bitti sonniss && bitti fsd50k && bitti commons; do sleep 300; done
echo "$(date +%T) indirmeler bitti"
SFX_DEVICE=cpu "$K/calistir.sh" ac
SFX_DEVICE=cpu SFX_WORKERS=64 "$K/calistir.sh" katalog
SFX_DEVICE=cpu SFX_THREADS=64 "$K/calistir.sh" gomme
SFX_DEVICE=cpu "$K/calistir.sh" rapor > /data/editor/sfx/_olcum/havuz-rapor.json
KAP="docker run --rm --network editor-net --env-file /data/editor/secrets/editor.env -u $(id -u):$(id -g) -e HOME=/tmp \
  -e PYTHONPATH=/src/src -v /data/editor/sfx:/data/editor/sfx -v $(cd "$K/../.." && pwd):/src:ro \
  --entrypoint python ${SFX_STUDIO_IMAGE:-editor-py-studio:sfx-deneme} /src/deploy/sfx/kapsama.py"
$KAP esle && $KAP secim && $KAP rapor
echo "$(date +%T) tamam"
