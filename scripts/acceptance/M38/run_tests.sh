#!/bin/sh
# M38 Müşteri ilişkileri ve CRM — test sunucusunda koşar (Mac'te koşmaz; AGENTS.md «bağlı gerçek DB ile test»).
# Kaynak git archive main'den oturuma özgü klasöre açılmış olmalı: /tmp/claude-<oturum>/src
#   sh scripts/acceptance/M38/run_tests.sh /tmp/claude-<oturum>/src
# 1) Birim testleri (saf işlevler + köprünün kendi tabloları; sqlite yalnız köprü tabloları için) ve M30 ortak kaynak testleri.
# 2) Uç düzeyi yetki taraması (test_access: her yolun kuralı var, hiçbir uç `request`'i sorgu parametresi sanmıyor).
# 3) Ön yüz: tsc + vitest (menü ↔ yetki kataloğu eşliği dahil).
# Gerçek DB kabulü ayrıca: gece turu elle (systemctl start timas-musteri@gece), reference_check.py (kanıt JSON'u),
# write_check.py (yazma uçları, kimlikler dosyaya), cleanup.py (o kimliklerle temizlik).
set -eu
SRC="${1:?kaynak klasörü}"
cd "$SRC/backend"
python3 -m pytest -q semantic_layer/tests/test_musteri.py semantic_layer/tests/test_field_sales.py semantic_layer/tests/test_access.py
cd "$SRC"
npx tsc -b
npx vitest run src/canvas/musteri src/canvas/field src/canvas/nav
