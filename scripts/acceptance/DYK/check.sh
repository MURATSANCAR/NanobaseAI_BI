#!/bin/bash
# DYK Kurul — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (DYK + yetki + veri güvenliği envanteri), tsc, vitest, derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı; KURUL_DIR geçici klasör),
#      timasai'nin 15 dk'lık oturumu açılır (yönetici olmayan ikinci oturum varsa COOKIE2).
#   4. kabul.py (panel ↔ doğrudan SQL R1–R6, kaynak modül uçları, gri kural, paket değişmezliği, Zeki AI özeti, yetki),
#      sonra cleanup.py --actor timasai (toplantı, karar, aksiyon, paket, PDF, dağıtım, iş); oturum satırları silinir;
#      Yönetim → Kişiler'de gerçek olmayan hesap kalmadığına bakılır.
#   5. timas-kurul.service bir kez elle koşturulur (hatırlatmalar yalnız iç adreslere; eşik ve sahip boş geldiği için
#      ilk koşuda yorum hatırlatması çıkmaz), sonra zamanlayıcı etkinleştirilir. VM'de jobs konteyneri günde bir çağırır.
# Kullanım: W=/tmp/claude-dyk ./check.sh
set -u
W=${W:-/tmp/claude-dyk}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (DYK + yetki + envanter)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_kurul.py \
  semantic_layer/tests/test_access.py semantic_layer/tests/test_data_security.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
