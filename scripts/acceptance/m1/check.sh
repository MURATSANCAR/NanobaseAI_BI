#!/bin/bash
# Aday ağaçta (git archive) köprü testleri + ön yüz tsc/vitest/build. Çalışma klasörü /tmp/claude-m1basvuru.
set -u
W=${W:-/tmp/claude-m1basvuru}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' | wc -l)"
cd $W/src/backend
echo "== pytest (M1 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_editorial_applications.py semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
