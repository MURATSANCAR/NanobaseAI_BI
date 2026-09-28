#!/bin/bash
# Ortak Zeki AI yapı taşları + öneri 1/2/3 — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (yapı taşları + eski çağrı yerlerinin testleri), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı + tahmin önbelleği),
#      timasai'nin 15 dk'lık oturumu açılır.
#   4. kabul.py (uçlar ↔ önbellek dosyası / doğrudan SQL), sonra temizlik.py; oturum satırı silinir.
# Kullanım: W=/tmp/claude-zeki ./check.sh
set -u
W=${W:-/tmp/claude-zeki}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (yapı taşları + sayı denetimi/maske kullanan modüller)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider \
  semantic_layer/tests/test_zeki_text.py semantic_layer/tests/test_forecast_client.py \
  semantic_layer/tests/test_finance.py semantic_layer/tests/test_field_sales.py semantic_layer/tests/test_budget.py \
  semantic_layer/tests/test_stock.py semantic_layer/tests/test_marketing.py semantic_layer/tests/test_marketing_creative.py \
  semantic_layer/tests/test_risk.py semantic_layer/tests/test_kurul.py semantic_layer/tests/test_school_visits.py \
  semantic_layer/tests/test_shipping.py semantic_layer/tests/test_supply.py semantic_layer/tests/test_distribution.py \
  semantic_layer/tests/test_dealers.py semantic_layer/tests/test_musteri.py semantic_layer/tests/test_support.py \
  semantic_layer/tests/test_okur.py semantic_layer/tests/test_trendyol.py semantic_layer/tests/test_hr_recruit.py \
  semantic_layer/tests/test_hr_performance.py semantic_layer/tests/test_mailbox.py semantic_layer/tests/test_tenders.py \
  semantic_layer/tests/test_pazar.py semantic_layer/tests/test_backlist.py semantic_layer/tests/test_access.py 2>&1 | tail -30
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
echo "== kabul (yan port köprüsü açıkken): BASE=... COOKIE=... PYTHONPATH=$W/src/backend python scripts/acceptance/zeki-ortak/kabul.py --out $W/kabul-kimlikler.json"
echo "== temizlik: ZK_BACKEND=$W/src/backend python scripts/acceptance/zeki-ortak/temizlik.py --ids-file $W/kabul-kimlikler.json --actor timasai --since <başlangıç>"
