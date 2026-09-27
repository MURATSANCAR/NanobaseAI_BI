#!/bin/bash
# Efekt havuzu — Sonniss #GameAudioGDC arşivleri (GPU'da çalışır; model/konteyner kullanmaz).
#
# Kaynak: resmî indirme sayfası https://sonniss.com/gameaudiogdc'deki «Mirror #1» = ftpmirror.your.org (2015-2020).
# Lisans: https://sonniss.com/gdc-bundle-license/ (ticari kullanım, atıfsız; ses dosyası olarak yeniden dağıtım yasak,
# yapay zekâ EĞİTİMİNDE kullanım yasak). Her yılın License.pdf'i de indirilir ve arşivle birlikte saklanır.
# 2021-2024: ana adres Cloudflare denetimi ister (aşılmaz), feralhosting aynası bağlantıyı kabul edip yanıt vermiyor
# → alınmadı (belge: docs/analiz/efekt-sesleri-kaynaklar.md).
#
# Kullanım: indir_sonniss.sh [hedef]   (varsayılan /data/editor/sfx/_indir/sonniss). Kaldığı yerden sürer (.ok işareti).
set -u
BASE=https://ftpmirror.your.org/pub/misc
OUT=${1:-/data/editor/sfx/_indir/sonniss}
mkdir -p "$OUT"
{
  echo "2015|$BASE/sonniss/sonniss.zip"
  echo "2016|$BASE/sonniss2016/Licensing.pdf"
  for i in 1 2 3 4 5 6; do echo "2016|$BASE/sonniss2016/Sonniss.com%20-%20GDC%202016-%20Game%20Audio%20Bundle%20Part%20${i}of6.zip"; done
  echo "2017|$BASE/sonniss2017/Licensing.pdf"
  for i in $(seq 1 9); do echo "2017|$BASE/sonniss2017/Sonniss.com%20-%20GDC%202017%20-%20Game%20Audio%20Bundle%20Part%20${i}of9.zip"; done
  echo "2018|$BASE/sonniss2018/License.pdf"
  for i in $(seq 1 8); do echo "2018|$BASE/sonniss2018/Sonniss.com%20-%20GDC%202018%20-%20Game%20Audio%20Bundle%20Part%20${i}of8.zip"; done
  echo "2019|$BASE/sonniss2019/License.pdf"
  for i in $(seq 1 8); do echo "2019|$BASE/sonniss2019/Sonniss.com%20-%20GDC%202019%20-%20Game%20Audio%20Bundle%20Part%20${i}of8.zip"; done
  echo "2020|$BASE/sonniss2020/License.pdf"
  for i in $(seq 1 14); do echo "2020|$BASE/sonniss2020/Sonniss.com%20-%20GDC%202020%20-%20Game%20Audio%20Bundle%20Part${i}of14.zip"; done
} > "$OUT/liste.txt"

fetch() {
  local year=${1%%|*} url=${1#*|}
  local name
  name=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.unquote(sys.argv[1].rsplit("/",1)[1]))' "$url")
  mkdir -p "$OUT/$year"
  [ -f "$OUT/$year/$name.ok" ] && return 0
  for _ in 1 2 3 4 5; do
    if wget -q -c --timeout=60 --tries=3 -O "$OUT/$year/$name" "$url"; then
      echo "$url" > "$OUT/$year/$name.ok"
      echo "$(date +%T) OK $year $name $(stat -c %s "$OUT/$year/$name")"
      return 0
    fi
    sleep 20
  done
  echo "$(date +%T) FAIL $year $name"
}
export -f fetch
export OUT
xargs -P 3 -I{} bash -c 'fetch "$@"' _ {} < "$OUT/liste.txt"
echo "$(date +%T) BITTI"
