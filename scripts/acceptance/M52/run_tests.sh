#!/bin/sh
# M52 Tedarik ve baskı — test sunucusunda koşar (Mac'te koşmaz; AGENTS.md «bağlı gerçek DB ile test»).
# Kaynak git archive main'den oturuma özgü klasöre açılmış olmalı: /tmp/claude-<oturum>/src
#   sh scripts/acceptance/M52/run_tests.sh /tmp/claude-<oturum>/src
# 1) Birim testleri (saf hesaplar + köprü uçlarının yetki davranışı; sqlite yalnız köprünün kendi tabloları için).
# 2) Uç düzeyi yetki taraması (test_access: her yolun kuralı var, hiçbir uç `request`'i sorgu parametresi sanmıyor).
# 3) Ön yüz: tsc + vitest (menü ↔ yetki kataloğu eşliği dahil).
# Gerçek DB kabulü ayrıca: kabul.py (kanıt JSON'u), sonra cleanup.py. Gece işi ilk kez elle:
#   systemctl start timas-supply.service   (sonra timer açılır; bellek: run-it-before-it-runs-itself)
set -eu
SRC="${1:?kaynak klasörü}"
cd "$SRC/backend"
python3 -m pytest -q semantic_layer/tests/test_supply.py semantic_layer/tests/test_access.py semantic_layer/tests/test_production.py
cd "$SRC"
npx tsc -b
npx vitest run src/canvas/nav
