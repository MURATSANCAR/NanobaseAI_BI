#!/bin/bash
# H2 Okuyucu veri tabanı — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (H2 + yetki), tsc, vitest, derleme.
#   3. Köprünün ortamına bir kez READERS_HASH_SALT eklenir (en az 16 karakter, rastgele; bir daha değişmez — değişirse
#      bütün okur kimlikleri yeniden kurulur): /etc/nanobase/semantic-bridge.env. Yan port köprüsü aday ağaçla
#      başlatılır (gerçek CRM + katalog veritabanı), timasai'nin 15 dk'lık oturumu açılır.
#   4. kabul.py (uçlar ↔ doğrudan CRM SQL, referans.sql R1–R10), sonra cleanup.py (segment + yükleme + değişiklik
#      kaydı); oturum satırı silinir; Yönetim → Kişiler'de gerçek olmayan hesap kalmadığına bakılır.
#   5. timas-readers.service bir kez elle koşturulur (READERS_ALERT_RECIPIENTS / READERS_KVKK_RECIPIENTS boşsa e-posta
#      gitmez), sonra zamanlayıcı etkinleştirilir. READERS_EXPORT_ENABLED hukuk teyidine kadar kapalı kalır.
# Kullanım: W=/tmp/claude-h2 ./check.sh
set -u
W=${W:-/tmp/claude-h2}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (H2 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_readers.py \
  semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
