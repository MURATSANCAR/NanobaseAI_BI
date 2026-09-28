#!/bin/bash
# M24 Katalog ve bülten — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M24 + yetki + pazarlama), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı), timasai'nin 15 dk'lık oturumu
#      açılır (yönetici: açık yetkiler katalog-bulten.onay ve bulten.segment dahil).
#   4. kabul.py (uçlar ↔ doğrudan SQL, referans.sql R1–R8), sonra cleanup.py --actor timasai --since <başlangıç>
#      (katalog, bülten, iş ve değişiklik kaydı), oturum satırları silinir; Yönetim → Kişiler'de gerçek olmayan hesap
#      kalmadığına bakılır.
#   5. timas-catalog.service bir kez elle koşturulur (CATALOG_ALERT_RECIPIENTS boşsa e-posta gitmez), sonra zamanlayıcı
#      etkinleştirilir. Portal hiçbir okura/bayiye e-posta göndermez.
# Kullanım: W=/tmp/claude-m24 ./check.sh
set -u
W=${W:-/tmp/claude-m24}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M24 + yetki + pazarlama)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_catalogs.py \
  semantic_layer/tests/test_access.py semantic_layer/tests/test_marketing.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
