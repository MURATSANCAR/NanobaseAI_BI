#!/bin/bash
# M45 Finansal raporlar — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M45 + yetki + bütçe + fiyatlama), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı), timasai'nin 15 dk'lık oturumu açılır.
#   4. kabul.py (uçlar ↔ doğrudan SQL, R1–R8), sonra temizlik.py (vergi kaydı + değişiklik kaydı), oturum satırı silinir.
#   5. Kurulumdan sonra timas-finance.service bir kez elle koşturulur, sonra zamanlayıcı etkinleştirilir.
# Kullanım: W=/tmp/claude-m45 ./check.sh
set -u
W=${W:-/tmp/claude-m45}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M45 + yetki + bütçe + fiyatlama)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_finance.py \
  semantic_layer/tests/test_access.py semantic_layer/tests/test_budget.py semantic_layer/tests/test_pricing_data.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
echo "== kabul (yan port köprüsü açıkken): BASE=... COOKIE=... PYTHONPATH=$W/src/backend python scripts/acceptance/M45/kabul.py --out $W/kabul-kimlikler.json"
echo "== temizlik: M45_BACKEND=$W/src/backend python scripts/acceptance/M45/temizlik.py --ids-file $W/kabul-kimlikler.json --actor timasai --since <başlangıç>"
