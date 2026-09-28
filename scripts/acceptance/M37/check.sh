#!/bin/bash
# M37 Okur topluluğu — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M37 + yetki), tsc, vitest (menü–katalog eşliği), derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek CRM + katalog veritabanı; H2 kuruluysa okur çekirdeği bağlı),
#      timasai'nin 15 dk'lık oturumu açılır (COOKIE).
#   4. kabul.py (uçlar ↔ doğrudan SQL, referans.sql R1–R8; H2 yoksa R1–R5 DOĞRULANAMADI), sonra temizlik.py
#      (segment + program + değişiklik kaydı), oturum satırı silinir; Yönetim → Kişiler'de gerçek olmayan hesap kalmadığına bakılır.
#   5. timas-okur.service bir kez elle koşturulur (OKUR_ALERT_RECIPIENTS boşsa e-posta gitmez), sonra zamanlayıcı etkinleştirilir.
# Kullanım: W=/tmp/claude-<oturum> ./check.sh
set -u
W=${W:?W=/tmp/claude-<oturum> verin}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M37 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_okur.py \
  semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
