#!/bin/bash
# Zeki AI öneri 4–8 (fark ayrıştırma, ne değişti, beklenen aralık, nakit bandı, destek olguları) — test sunucusunda kabul
# (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest, tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + katalog veritabanı), timasai'nin 15 dk'lık oturumu açılır.
#   4. Nakit tablosu yeniden kurulur (bant için: POST /api/v1/finance/cash/rebuild; tahmin servisi haftalık seride ölçülecek).
#   5. kabul.py, sonra temizlik.py; oturum satırı silinir.
# Kullanım: W=/tmp/claude-zf ./check.sh
set -u
W=${W:-/tmp/claude-zf}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider \
  semantic_layer/tests/test_zeki_fark.py semantic_layer/tests/test_alerts.py semantic_layer/tests/test_report_mail.py \
  semantic_layer/tests/test_finance.py semantic_layer/tests/test_budget.py semantic_layer/tests/test_support.py \
  semantic_layer/tests/test_zeki_text.py semantic_layer/tests/test_forecast_client.py semantic_layer/tests/test_access.py 2>&1 | tail -30
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
echo "== kabul (yan port köprüsü açıkken): BASE=... COOKIE=... PYTHONPATH=$W/src/backend python scripts/acceptance/zeki-fark/kabul.py --out $W/kabul-kimlikler.json"
echo "== temizlik: ZK_BACKEND=$W/src/backend python scripts/acceptance/zeki-fark/temizlik.py --ids-file $W/kabul-kimlikler.json --user timasai"
