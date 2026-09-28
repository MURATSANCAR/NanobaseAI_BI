#!/bin/bash
# M43 Depo ve stok — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M43 + yetki + M29/M12 komşuları), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı; STOCK_CACHE_DIR geçici klasöre),
#      timasai'nin 15 dk'lık oturumu açılır.
#   4. kabul.py (uçlar ↔ doğrudan SQL, R1–R11), sonra cleanup.py (taslak eşik, not, değişiklik kaydı), oturum satırı silinir.
#   5. Kurulumdan sonra timas-stock.service bir kez elle koşturulur (gece fotoğrafı, öneri, bülten), sonra zamanlayıcı açılır.
# Kullanım: W=/tmp/claude-m43 ./check.sh
set -u
W=${W:-/tmp/claude-m43}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M43 + yetki + komşular)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_stock.py \
  semantic_layer/tests/test_access.py semantic_layer/tests/test_distribution.py semantic_layer/tests/test_production.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
echo "== sonraki adım: yan port köprüsü + kabul.py --out $W/kabul-kimlikler.json + cleanup.py --ids-file $W/kabul-kimlikler.json --actor timasai --since <başlangıç>"
