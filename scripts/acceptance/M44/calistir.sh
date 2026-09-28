#!/bin/bash
# M44 Lojistik ve kargo — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M44 + yetki), tsc, vitest, derleme.
#   3. Önce ölçüm: `python kabul.py --olcum` (yazmaz) → entegrasyon sonuç değerleri, kargo kaydı tarih biçimleri, iade /
#      tahsilatlı değerleri ve takip no eşleşme payı. Farklıysa yönetim ekranındaki SHIPPING_* ayarları düzeltilir
#      (SHIPPING_INTEGRATION_OK_VALUES, SHIPPING_CARGO_DATE_FORMATS, SHIPPING_RETURN_NO_VALUES, SHIPPING_COD_NO_VALUES,
#      SHIPPING_UNTRACKED_EXCLUDE_TYPES). Kargo firması tablosunda yalnız ad ve kod okunur.
#   4. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı), timasai'nin 15 dk'lık oturumu açılır.
#   5. kabul.py (uçlar ↔ doğrudan SQL, referans.sql R1–R8), sonra temizlik.py (taslak + karar + değişiklik kaydı),
#      oturum satırı silinir; Yönetim → Kişiler'de gerçek olmayan hesap kalmadığına bakılır.
#   6. Kurulumdan sonra timas-shipping.service bir kez elle `?gorev=gunluk` ile koşturulur (alıcı ayarı boşsa e-posta
#      gitmez; hata sınıflaması LLM kapısından BATCH), sonra timas-shipping.timer etkinleştirilir.
# Kullanım: W=/tmp/claude-m44 ./calistir.sh
set -u
W=${W:-/tmp/claude-m44}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M44 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_shipping.py \
  semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest (kargo + menü)"
timeout 900 npx vitest run src/canvas/shipping src/canvas/nav 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
