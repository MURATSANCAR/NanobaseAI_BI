#!/bin/bash
# Sorgu bilgisi — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (sorgu bilgisi + bütçe + finans + fiyatlama), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır, timasai'nin kısa oturumu açılır.
#   4. kabul.py (K1–K3 her uçta, R1–R6 doğrudan SQL). Kabul hiçbir yere yazmaz; temizlik = oturum satırı + $W.
# Kullanım: W=/tmp/claude-sorgu ./check.sh
set -u
W=${W:-/tmp/claude-sorgu}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_sorgu_bilgisi.py \
  semantic_layer/tests/test_budget.py semantic_layer/tests/test_finance.py semantic_layer/tests/test_pricing_data.py \
  semantic_layer/tests/test_pricing_store.py semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== envanter denetimi (menü + rota ↔ docs/analiz/sorgu-bilgisi-envanteri.md)"
python3 scripts/analiz/sorgu_bilgisi_envanter.py | tail -5
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run src/canvas/components/sqlInfo.test.ts src/canvas/nav 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
echo "== kabul (yan port köprüsü açıkken):"
echo "   BASE=http://127.0.0.1:8798 COOKIE=... SEMANTIC_CONNECTION_FILE=... SEMANTIC_STORE_DSN=... \\"
echo "   PYTHONPATH=$W/src/backend python scripts/acceptance/sorgu-bilgisi/kabul.py [--skip-heavy]"
echo "== temizlik: timasai kısa oturum satırını sil; rm -rf $W"
