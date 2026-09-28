#!/bin/bash
# M40 Trendyol — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M40 + M42 + yetki), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + katalog veritabanı), timasai'nin 15 dk'lık oturumu açılır.
#   4. kabul.py (uçlar ↔ doğrudan SQL, referans.sql K1–K7; Logo okumasını kendisi başlatır ve bekler). Gerçek panel
#      dosyası varsa M40_URUN_DOSYASI=<yol> ile K3 de koşar ve yükleme kabul sonunda silinir. Sonra
#      temizlik.py --since <kabul.py'nin yazdığı an>; oturum satırı silinir; Yönetim → Kişiler'de gerçek olmayan hesap yok.
#   5. timas-channels.service bir kez elle koşturulur (M42 gece okuması + Trendyol + Amazon adımları).
#   6. Ekran: /timas/trendyol, /trendyol/urunler, /trendyol/siparisler, /trendyol/sorular, /trendyol/vitrin,
#      /trendyol/haftalik, /trendyol/yukle — 320/390/768 px ve masaüstünde yatay taşma yok; ekranda teknoloji adı yok.
# Kullanım: W=/tmp/claude-m40 ./check.sh
set -u
W=${W:-/tmp/claude-m40}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M40 + M41 + M42 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_trendyol.py \
  semantic_layer/tests/test_amazon.py semantic_layer/tests/test_channels.py semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
