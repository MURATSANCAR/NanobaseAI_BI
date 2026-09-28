#!/bin/bash
# AI fırsatları öneri 15 (okur sesi), 16 (not sinyali), 17 (lansman risk + ay planı boşluğu), 19 (Kampüs «Bugün») —
# test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (dört yeni test + etkilenen modüller + yetki), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek katalog veritabanı), timasai'nin 15 dk'lık oturumu açılır.
#   4. kabul.py --gece (iki gece turu bir kez elle; sonra K1–K11 uç ↔ doğrudan SQL). Sonra temizlik.py --since <başlangıç>;
#      oturum satırı silinir; Yönetim → Kişiler'de gerçek olmayan hesap yok.
#   5. Zamanlayıcılar kurulur ve bir kez elle koşturulur: timas-okur-sesi.service, timas-not-sinyali.service
#      (lansman cümlesi mevcut timas-marketing-launch turunda).
#   6. Ekran: /timas/okur-toplulugu/yorumlar, /trendyol/sorular, /trendyol/siparisler (İadeler), /saha/musteri/:kod,
#      /bayi-risk/:kod, /musteri-iliskileri/cari/:kod, /pazarlama/lansman, /pazarlama/aylik-plan/:ay?sekme=butce,
#      Kampüs «Bugün» düğmesi — 320/390/768 px ve masaüstünde yatay taşma yok; ekranda teknoloji adı yok.
# Kullanım: W=/tmp/claude-zeki ./check.sh
set -u
W=${W:-/tmp/claude-zeki}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider \
  semantic_layer/tests/test_reader_voice.py semantic_layer/tests/test_note_signal.py \
  semantic_layer/tests/test_marketing_launch_risk.py semantic_layer/tests/test_today_brief.py \
  semantic_layer/tests/test_marketing_launch.py semantic_layer/tests/test_marketing_monthly.py \
  semantic_layer/tests/test_trendyol.py semantic_layer/tests/test_okur.py semantic_layer/tests/test_field_sales.py \
  semantic_layer/tests/test_dealers.py semantic_layer/tests/test_musteri.py semantic_layer/tests/test_access.py 2>&1 | tail -30
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run src/canvas/signals 2>&1 | tail -12
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
