#!/bin/bash
# Efekt havuzu — FSD50K (Freesound kliplerinden derlenmiş veri kümesi), resmî Zenodo kaydı 4060432:
# https://zenodo.org/records/4060432 . Her klibin lisansı Freesound yükleyicisinindir ve
# FSD50K.metadata/{dev,eval}_clips_info_FSD50K.json'da yazılıdır (CC0, CC-BY 3.0, CC-BY-NC 3.0, CC Sampling+).
# Havuza YALNIZ CC0 ve CC-BY klipler alınır (sfx_havuz.py süzer); NC ve Sampling+ klipler diskte arşivde kalır,
# kataloğa girmez. CC-BY klipler kitap sonundaki «ses efektleri kaynakçası»na yazar/başlık/bağlantıyla girer.
# Kullanım: indir_fsd50k.sh [hedef]   (varsayılan /data/editor/sfx/_indir/fsd50k). Kaldığı yerden sürer.
set -u
OUT=${1:-/data/editor/sfx/_indir/fsd50k}
REC=https://zenodo.org/api/records/4060432/files
mkdir -p "$OUT"
cd "$OUT" || exit 1
for f in FSD50K.doc.zip FSD50K.metadata.zip FSD50K.ground_truth.zip \
         FSD50K.dev_audio.z01 FSD50K.dev_audio.z02 FSD50K.dev_audio.z03 FSD50K.dev_audio.z04 FSD50K.dev_audio.z05 \
         FSD50K.dev_audio.zip FSD50K.eval_audio.z01 FSD50K.eval_audio.zip; do
  [ -f "$f.ok" ] && continue
  for _ in 1 2 3 4 5; do
    if wget -q -c --timeout=60 --tries=3 -O "$f" "$REC/$f/content"; then
      echo "$REC/$f/content" > "$f.ok"; echo "$(date +%T) OK $f $(stat -c %s "$f")"; break
    fi
    sleep 20
  done
  [ -f "$f.ok" ] || echo "$(date +%T) FAIL $f"
done
# Zenodo kaydındaki md5'lerle doğrulama
curl -s --max-time 60 https://zenodo.org/api/records/4060432 | python3 -c '
import json, sys, hashlib, os
r = json.load(sys.stdin)
for f in r["files"]:
    k, want = f["key"], f["checksum"].split(":", 1)[1]
    if not os.path.exists(k):
        print("YOK", k); continue
    h = hashlib.md5()
    with open(k, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 22), b""):
            h.update(b)
    print("MD5", "OK" if h.hexdigest() == want else "HATALI", k)
'
echo "$(date +%T) BITTI"
