#!/bin/bash
# M27 Fuar, etkinlik ve ödül — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M27 + yetki), tsc, vitest (menü–katalog eşliği), derleme, Kampüs yer tutucusu denetimi.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek Logo + CRM + katalog veritabanı; EVENTS_DIR geçici klasör),
#      timasai'nin 15 dk'lık oturumu açılır.
#   4. kabul.py (salt okunur: R4–R8), sonra kabul.py --write (deneme kartı: R1, R2, R3, R7, öneri, iki göz onayı; kart
#      sonunda API'den silinir), cleanup.py (kalan değişiklik kaydı), oturum satırı silinir; Yönetim → Kişiler kontrolü.
#   5. Tip eşlemesi: «Zeki AI önerisi al» bir kez (371 tip, BATCH önceliği; süre ve «seçemedi» sayısı günlüğe),
#      öneriler insan kararı olmadan takvime girmez. R4 ancak «fuar» kararı verildikten sonra GEÇTİ olabilir.
#   6. timas-events.service bir kez elle koşturulur (çıktıdaki hatırlatma ve sonuç sayıları günlüğe), sonra
#      zamanlayıcı etkinleştirilir. Dış gönderim yok.
#   7. Telefon: 320 / 390 / 768 / masaüstü — takvim, fuar kartı (görev işaretleme, gider + fiş fotoğrafı), sonuç,
#      ödüller, tip eşlemesi, Kampüs ajanda kartı.
# Kullanım: W=/tmp/claude-m27 ./check.sh
set -u
W=${W:-/tmp/claude-m27}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
echo "== Kampüs yer tutucusu kaldı mı (0 olmalı): $(grep -rn 'TÜYAP Fuarı 2024\|Dünya Kitap ve Telif Hakları Günü\|Aylık Yayın Kurulu Değerlendirmesi' src | wc -l)"
cd $W/src/backend
echo "== pytest (M27 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_events.py \
  semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest (menü–katalog eşliği dahil)"
timeout 900 npx vitest run src/canvas/nav 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
cat <<'EOF'
== sonraki adımlar (elle)
1. Yan port köprüsü (aday ağaç) + timasai kısa oturumu:
   BASE=http://127.0.0.1:8798 COOKIE='timas_session=…' PYTHONPATH=$W/src/backend \
     /data/nanobaseai/bi/semantic-venv/bin/python scripts/acceptance/M27/kabul.py --out $W/kabul-kimlikler.json
   … aynı komut --write ile (deneme kartı açar ve siler)
2. M27_BACKEND=$W/src/backend python scripts/acceptance/M27/cleanup.py --ids-file $W/kabul-kimlikler.json \
     --actor timasai --since <koşu başlangıcı>
3. systemctl start timas-events.service && journalctl -u timas-events -n 50 ; sonra systemctl enable --now timas-events.timer
EOF
