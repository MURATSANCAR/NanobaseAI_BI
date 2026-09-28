#!/bin/bash
# M33 İhale takibi — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M33 + yetki + bütçe), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı; TENDER_DIR geçici klasör),
#      timasai'nin 15 dk'lık oturumu açılır (ihale.karar yetkisi olmayan ikinci oturum varsa COOKIE2).
#   4. kabul.py (uçlar ↔ doğrudan SQL, referans.sql R1–R6), sonra cleanup.py (ihale + dosya + değişiklik kaydı),
#      oturum satırları silinir; Yönetim → Kişiler'de gerçek olmayan hesap kalmadığına bakılır.
#   5. timas-tenders.service bir kez elle koşturulur (TENDER_ALERT_RECIPIENTS boşsa e-posta gitmez), sonra zamanlayıcı
#      etkinleştirilir. Müşteri VM'inde TENDER_WATCH_ENABLED kapalı kalır.
# Kullanım: W=/tmp/claude-m33 ./check.sh
set -u
W=${W:-/tmp/claude-m33}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M33 + yetki + bütçe)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_tenders.py \
  semantic_layer/tests/test_access.py semantic_layer/tests/test_budget.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
