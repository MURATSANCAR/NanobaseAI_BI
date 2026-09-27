#!/bin/sh
# M30 Saha satış ve tahsilat — test sunucusunda koşar (Mac'te koşmaz; AGENTS.md «bağlı gerçek DB ile test»).
# Kaynak git archive main'den oturuma özgü klasöre açılmış olmalı: /tmp/claude-<oturum>/src
#   sh scripts/acceptance/M30/run_tests.sh /tmp/claude-<oturum>/src
# 1) Birim testleri (saf işlevler + köprü uç kuralları; sqlite yalnız köprünün kendi tabloları için).
# 2) Uç düzeyi yetki taraması (test_access: her yolun kuralı var, hiçbir uç `request`'i sorgu parametresi sanmıyor).
# 3) Ön yüz: tsc + vitest (menü ↔ yetki kataloğu eşliği dahil).
# Gerçek DB kabulü ayrıca: reference_check.py (kanıt JSON'u), sonra cleanup.py.
set -eu
SRC="${1:?kaynak klasörü}"
cd "$SRC/backend"
python3 -m pytest -q semantic_layer/tests/test_field_sales.py semantic_layer/tests/test_access.py
cd "$SRC"
npx tsc -b
npx vitest run src/canvas/field src/canvas/nav
