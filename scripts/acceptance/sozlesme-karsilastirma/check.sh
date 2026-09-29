#!/bin/bash
# Sözleşme karşılaştırma — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç $W'ye açılır (git archive; ._* sayısı 0 olmalı), node_modules canlı ağaçtan bağlanır.
#   2. Bu betik: pytest, tsc, vitest, derleme.
#   3. Yan köprü aday ağaçla (administrator kullanıcısıyla; SEMANTIC_CALLER_TOKEN satırı çıkarılmış ortam kopyası,
#      CONTRACT_COMPARE_DIR ve CONTRACT_DOCS_DIR $W/var altına) :8801'de başlatılır; timasai'nin 15 dk'lık oturumu açılır.
#   4. kabul.py (uçlar ↔ doğrudan CRM SQL / betiğin kendi okuduğu PDF); kabul kendi yüklediklerini ve okumalarını siler.
#      Oturum satırı, ortam kopyası ve yan köprü iş bitince kaldırılır; timasai'nin değişiklik kaydı satırları kalır.
# Kullanım: W=/tmp/claude-sozkars ./check.sh
set -u
W=${W:-/tmp/claude-sozkars}
cd $W || exit 1
echo "== ._ sayısı: $(find $W -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/backend
echo "== pytest"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider \
  semantic_layer/tests/test_contracts_compare.py semantic_layer/tests/test_contracts.py semantic_layer/tests/test_contract_extract.py \
  semantic_layer/tests/test_access.py semantic_layer/tests/test_admin_categories.py 2>&1 | tail -5
cd $W
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -20; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -6
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -4
echo "== kabul: sudo systemd-run --pipe --wait --uid=administrator -p EnvironmentFile=\$W/side.env --setenv=BASE=http://127.0.0.1:8801 --setenv=COOKIE=... python scripts/acceptance/sozlesme-karsilastirma/kabul.py --out \$W/kabul.json"
