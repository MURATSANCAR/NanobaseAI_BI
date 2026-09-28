#!/bin/bash
# M41 Amazon ve yurtdışı — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M41 + M40 + M42 + yetki), tsc, vitest, derleme (M40 check.sh ile aynı; biri koşulması yeter).
#   3. Yan port köprüsü aday ağaçla (gerçek Logo + CRM + katalog veritabanı), timasai'nin 15 dk'lık oturumu.
#   4. Önce M42 kabulü (kanal önbelleği ve eşleme) — K2 ve konsinyenin «bu yıl faturalanan» sütunu onu okur.
#   5. kabul.py (uçlar ↔ doğrudan SQL, referans.sql K1–K7; okumayı kendisi başlatır). İsteğe bağlı M41_TASLAK=<stok kodu>
#      tek taslak yazar. Sonra temizlik.py --since <an> [--drafts <id>]; oturum satırı silinir; Yönetim → Kişiler temiz.
#   6. timas-channels.service bir kez elle (M42 + M40 + M41 adımları); CRM hatası kayda düşer, Logo kısmı yine yazılır.
#   7. Ekran: /timas/amazon, /amazon/konsinye, /amazon/yurtdisi, /amazon/haklar, /amazon/pazarlar, /amazon/taslaklar —
#      320/390/768 px ve masaüstünde yatay taşma yok; ekranda teknoloji adı yok.
# Kullanım: W=/tmp/claude-m41 ./check.sh
set -u
W=${W:-/tmp/claude-m41}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M41 + M40 + M42 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_amazon.py \
  semantic_layer/tests/test_trendyol.py semantic_layer/tests/test_channels.py semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
