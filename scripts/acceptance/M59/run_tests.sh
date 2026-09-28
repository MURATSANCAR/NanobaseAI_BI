#!/bin/sh
# M59 Bayi riski — test sunucusunda koşar (Mac'te koşmaz; AGENTS.md «bağlı gerçek DB ile test»).
# Kaynak git archive main'den oturuma özgü klasöre açılmış olmalı: /tmp/claude-<oturum>/src
#   sh scripts/acceptance/M59/run_tests.sh /tmp/claude-<oturum>/src
# 1) Birim testleri: M59 saf işlevleri + köprünün kendi tabloları (sqlite) + M30 testleri (ortak kaynak fonksiyonları
#    değişmedi mi) + uç düzeyi yetki taraması.
# 2) Ön yüz: tsc + vitest (menü ↔ yetki kataloğu eşliği dahil).
# Gerçek DB kabulü ayrıca: reference_check.py (kanıt JSON'u), write_check.py, sonra cleanup.py.
set -eu
SRC="${1:?kaynak klasörü}"
cd "$SRC/backend"
python3 -m pytest -q semantic_layer/tests/test_dealers.py semantic_layer/tests/test_field_sales.py semantic_layer/tests/test_access.py
cd "$SRC"
npx tsc -b
npx vitest run src/canvas/dealers src/canvas/field src/canvas/nav
