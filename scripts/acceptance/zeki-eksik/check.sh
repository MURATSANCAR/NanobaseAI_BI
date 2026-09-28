#!/bin/bash
# Eksik tamamlama (öneri 18 hak haritası, finansal denetim açıklama + kümeleme, ihale risk işaretleme, telif kapak
# e-postası + koşu özeti, SEO fırsattan öneri) — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive <dal>` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest, tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı), timasai'nin 15 dk'lık oturumu.
#   4. kabul.py, sonra temizlik.py; oturum satırı silinir.
# Kullanım: W=/tmp/claude-ze ./check.sh
set -u
W=${W:-/tmp/claude-ze}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider \
  semantic_layer/tests/test_rights_map.py semantic_layer/tests/test_rights_notes.py semantic_layer/tests/test_royalty.py \
  semantic_layer/tests/test_royalty_draft.py semantic_layer/tests/test_dijital.py \
  semantic_layer/tests/test_financial_audit_explain.py semantic_layer/tests/test_tenders_risk.py semantic_layer/tests/test_tenders.py \
  semantic_layer/tests/test_seo_propose_target.py semantic_layer/tests/test_seo_impact_opps.py \
  semantic_layer/tests/test_zeki_text.py semantic_layer/tests/test_access.py 2>&1 | tail -30
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
echo "== kabul (yan port köprüsü açıkken): BASE=... COOKIE=... [ZE_IHALE=<ihale>] PYTHONPATH=$W/src/backend python scripts/acceptance/zeki-eksik/kabul.py --out $W/kabul-kimlikler.json"
echo "== temizlik: ZK_BACKEND=$W/src/backend python scripts/acceptance/zeki-eksik/temizlik.py --ids-file $W/kabul-kimlikler.json"
