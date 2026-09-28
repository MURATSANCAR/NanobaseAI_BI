#!/bin/bash
# M23 İşbirlikleri — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M23 + yetki + serbest çalışan + pazarlama denetimi), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek CRM + katalog veritabanı), timasai'nin 15 dk'lık oturumu açılır.
#      İsteğe bağlı: COOKIE2 = işbirliği onay yetkisi olan ikinci oturum (teklif onayı, ücretli akış, ödeme satırı),
#      COOKIE3 = onay/ödeme yetkisi olmayan oturum (ücretin gizlenmesi). Yoksa o adımlar «ATLANDI (DOĞRULANAMADI)».
#   4. kabul.py (uçlar ↔ doğrudan SQL, referans.sql R1–R5), sonra cleanup.py (kişi + işbirliği + değişiklik kaydı),
#      oturum satırları silinir; Yönetim → Kişiler'de gerçek olmayan hesap kalmadığına bakılır.
#   5. timas-influencers.service bir kez elle koşturulur (INFLUENCER_*_RECIPIENTS boşsa e-posta gitmez), sonra
#      zamanlayıcı etkinleştirilir. INFLUENCER_API_ENABLED müşteri VM'inde kapalı kalır.
# Kullanım: W=/tmp/claude-m23 ./check.sh
set -u
W=${W:-/tmp/claude-m23}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M23 + yetki + serbest çalışan + pazarlama)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_influencers.py \
  semantic_layer/tests/test_access.py semantic_layer/tests/test_freelance.py semantic_layer/tests/test_marketing.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
