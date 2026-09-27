#!/bin/bash
# M31 aday ağaç denetimi (test sunucusunda): köprü testleri + ön yüz tsc/vitest/build. Çalışma klasörü oturuma özgü.
# Sonra: run-due elle (gece + haftalık), compare.py (gerçek DB kabulü), cleanup.py (yazılan kabul kaydı).
set -u
W=${W:-/tmp/claude-m31}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M31 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_school_visits.py \
  semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest (menü–katalog eşliği dahil)"
timeout 900 npx vitest run src/canvas/nav 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
cat <<'EOF'
== sonraki adımlar (elle)
1. Köprü yeni kodla yüklendikten sonra ilk gece işi elle:
   curl -fsS -m 3500 -X POST -H "X-Semantic-Caller: $SEMANTIC_CALLER_TOKEN" "http://127.0.0.1:8795/api/v1/schools/run-due?kind=nightly"
   (süre, okul sayısı, geçmiş bağ sayısı, ad eşleşmesi: asked/matched/unsure/pending günlüğe)
2. timasai kısa oturumuyla: ADMIN_COOKIE=… [REP_COOKIE=…] python compare.py [--write]
3. python cleanup.py --file /tmp/claude-m31/created.json ; oturum satırı silinir; Yönetim → Kişiler kontrolü.
4. Telefon: 320 / 390 / 768 / masaüstü — Bu hafta, okul kartı, rapor sayfası, katalog, bayi kuyruğu.
EOF
