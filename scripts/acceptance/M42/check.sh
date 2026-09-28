#!/bin/bash
# M42 Platform ve kanallar — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M42 + yetki + bütçe + pazarlama), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı), timasai'nin 15 dk'lık oturumu açılır.
#   4. kabul.py (uçlar ↔ doğrudan SQL, referans.sql R1–R8; okumayı kendisi başlatır ve bekler), sonra
#      temizlik.py --since <kabul.py'nin yazdığı an> (değişiklik kaydı satırları); oturum satırı silinir; Yönetim → Kişiler'de
#      gerçek olmayan hesap kalmadığına bakılır.
#   5. timas-channels.service bir kez elle koşturulur (gece okuması + eşleme adayları), sonra timas-channels.timer ve
#      timas-channels-report.timer etkinleştirilir (CHANNEL_REPORT_RECIPIENTS boşsa e-posta gitmez).
#   6. Ekran: /timas/kanallar, /kanallar/<platform>, /kanallar/matris, /kanallar/d2c, /kanallar/eslesme — 320/390/768 px ve
#      masaüstünde yatay taşma yok; marj yetkisi olmayan oturumda maliyet/marj alanı hiç görünmez.
# Kullanım: W=/tmp/claude-m42 ./check.sh
set -u
W=${W:-/tmp/claude-m42}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M42 + yetki + bütçe + pazarlama)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_channels.py \
  semantic_layer/tests/test_access.py semantic_layer/tests/test_budget.py semantic_layer/tests/test_marketing.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
