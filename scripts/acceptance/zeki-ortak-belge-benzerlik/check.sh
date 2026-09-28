#!/bin/bash
# Ortak yapı taşı 4 (belge okuma + OCR) ve 5 (kitap benzerliği) + öneri 9, 10, 20 — test sunucusunda kabul (yerelde
# koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest, editör testleri (kart imajında), tsc, vitest, derleme.
#   3. GPU'da kart servisi aday ağacın apps/editor'üyle yeniden kurulur (EDITOR_CARDS_IMAGE); `POST /v1/read` canlı.
#   4. Yan port köprüsü aday ağaçla başlatılır (gerçek CRM + Logo + katalog veritabanı + BI_EMBED_URL); timasai'nin
#      15 dk'lık oturumu açılır. Dizin ilk kez: `curl -X POST -H "X-Semantic-Caller: $TOKEN" $BASE/api/v1/books/similar/run-due`
#      (bitmezse tekrar; her tur yalnız kalan kitapları gömer).
#   5. kabul.py (uçlar ↔ doğrudan SQL / bilinen metin), sonra temizlik.py; oturum satırı silinir.
# Kullanım: W=/tmp/claude-benzerlik ./check.sh
set -u
W=${W:-/tmp/claude-benzerlik}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider \
  semantic_layer/tests/test_doc_read.py semantic_layer/tests/test_book_similarity.py \
  semantic_layer/tests/test_model_quality_clusters.py semantic_layer/tests/test_model_quality.py \
  semantic_layer/tests/test_tenders.py semantic_layer/tests/test_hr_recruit.py semantic_layer/tests/test_hr_learning.py \
  semantic_layer/tests/test_pazar.py semantic_layer/tests/test_marketing.py semantic_layer/tests/test_seo_similar_keymap.py \
  semantic_layer/tests/test_editorial_applications.py semantic_layer/tests/test_access.py semantic_layer/tests/test_admin*.py 2>&1 | tail -30
echo "== editör testi (kart imajında): docker run --rm -v $W/src/apps/editor:/app \$EDITOR_CARDS_IMAGE python /app/tests/test_portal_read.py"
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
echo "== kabul: BASE=... COOKIE=... SEMANTIC_STORE_DSN=... PYTHONPATH=$W/src/backend python scripts/acceptance/zeki-ortak-belge-benzerlik/kabul.py --out $W/kabul.json"
echo "== temizlik: PYTHONPATH=$W/src/backend python scripts/acceptance/zeki-ortak-belge-benzerlik/temizlik.py --ids-file $W/kabul.json --actor timasai --since <başlangıç>"
