#!/bin/bash
# Kapsama ölçümünde karşılanmayan ipuçlarını yerelde üretir, havuza ekler ve ölçümü yeniden koşar:
#   uret.sh uret --liste _olcum/karsilanmayan.json → havuz.py katalog uretim → gomme (işlemci) → kapsama secim/rapor
# GPU'da arka planda: setsid nohup kod/deploy/sfx/bosluk_doldur.sh > bosluk.log 2>&1 &
# Üretim kartı SFX_GPU (varsayılan 1); uret.py her seste kartta yer ve stüdyoda süren iş yokluğunu denetler.
set -eu
K=$(cd "$(dirname "$0")" && pwd)
O=/data/editor/sfx/_olcum
cp "$O/karsilanmayan.json" "$O/karsilanmayan-uretim-oncesi.json"
SFX_GPU=${SFX_GPU:-1} SFX_GPU_FRACTION=${SFX_GPU_FRACTION:-0.2} "$K/uret.sh" uret --liste "$O/karsilanmayan-uretim-oncesi.json"
SFX_DEVICE=cpu "$K/calistir.sh" katalog uretim
SFX_DEVICE=cpu SFX_THREADS=64 "$K/calistir.sh" gomme
KAP="docker run --rm --network editor-net --env-file /data/editor/secrets/editor.env -u $(id -u):$(id -g) -e HOME=/tmp \
  -e PYTHONPATH=/src/src -v /data/editor/sfx:/data/editor/sfx -v $(cd "$K/../.." && pwd):/src:ro \
  --entrypoint python ${SFX_STUDIO_IMAGE:-editor-py-studio:sfx-deneme} /src/deploy/sfx/kapsama.py"
cp "$O/rapor.json" "$O/rapor-uretim-oncesi.json"
$KAP secim && $KAP rapor
echo "$(date +%T) boşluk doldurma tamam"
