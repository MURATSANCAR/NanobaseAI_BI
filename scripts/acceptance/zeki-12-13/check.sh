#!/bin/bash
# Öneri 12 (başvuru ön okuması + editör raporu taslağı) ve 13 (sözleşme belgesinden şart çıkarma) — test sunucusunda
# kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest, tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek CRM + katalog veritabanı + LLM kapısı + BI_EMBED_URL; taranmış
#      sayfa için kart servisi); timasai'nin 15 dk'lık oturumu açılır. EDITORIAL_APPLICATIONS_DIR ve CONTRACT_DOCS_DIR
#      canlı köprüyle aynı klasörler olmalı (yan köprü administrator kullanıcısıyla: bellek side-port-bridge-user).
#   4. kabul.py (uçlar ↔ doğrudan SQL / betiğin kendi okuduğu belge metni), sonra temizlik.py; oturum satırı silinir.
# Kullanım: W=/tmp/claude-zeki1213 ./check.sh
set -u
W=${W:-/tmp/claude-zeki1213}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider \
  semantic_layer/tests/test_application_preread.py semantic_layer/tests/test_contract_extract.py \
  semantic_layer/tests/test_doc_read.py semantic_layer/tests/test_editorial_applications.py semantic_layer/tests/test_contracts.py \
  semantic_layer/tests/test_book_similarity.py semantic_layer/tests/test_access.py semantic_layer/tests/test_admin*.py 2>&1 | tail -30
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run src/canvas/editorial/applications/preread.test.ts src/canvas/editorial/contracts/extract.test.ts 2>&1 | tail -12
timeout 900 npx vitest run 2>&1 | tail -6
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
echo "== kabul: BASE=... COOKIE=... SEMANTIC_STORE_DSN=... PYTHONPATH=$W/src/backend python scripts/acceptance/zeki-12-13/kabul.py --out $W/kabul.json [--app-id <gerçek başvuru>]"
echo "== temizlik: PYTHONPATH=$W/src/backend python scripts/acceptance/zeki-12-13/temizlik.py --ids-file $W/kabul.json"
