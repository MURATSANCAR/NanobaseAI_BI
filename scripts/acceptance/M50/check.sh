#!/bin/bash
# M50 Zeki AI kalitesi — test sunucusunda kabul (yerelde koşulmaz). Sıra:
#   1. Aday ağaç `git archive main` ile $W/src'ye açılır (._* sayısı 0 olmalı).
#   2. Bu betik: pytest (M50 + yetki + yönetim), tsc, vitest (menü ↔ katalog), derleme.
#   3. Yan port köprüsü aday ağaçla başlatılır (gerçek katalog veritabanı; canlı köprü yeniden başlatılmaz),
#      timasai'nin 15 dk'lık oturumu açılır (COOKIE).
#   4. kabul.py --gate $W/src (okuma kapısı --report ile bir kez; uçlar ↔ doğrudan SQL R1–R9; geri bildirim yazımı),
#      sonra cleanup.py (soru kaydı, geri bildirim, koşu, sürüm satırı, değişiklik kaydı); oturum satırı silinir;
#      Yönetim → Kişiler'de gerçek olmayan hesap kalmadığına bakılır.
#   5. Soru hattı etkilenmedi: `resolver-gate.py tests/text2sql/set100.jsonl` (--report'suz) farksız çıkmalı.
#   6. Birimler kurulur: timas-model-quality@.service + sira/gece/hafta/ozet zamanlayıcıları; önce
#      `systemctl start timas-model-quality@gece.service` elle koşturulur, sonra zamanlayıcılar etkinleştirilir.
#      Cevap kapısı (hafta) ilk kez gündüz değil gece elle denenir (~35 dk, Zeki AI kapasitesi).
# Kullanım: W=/tmp/claude-m50 ./check.sh
set -u
W=${W:-/tmp/claude-m50}
cd $W/src || exit 1
echo "== ._ sayısı: $(find $W/src -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
cd $W/src/backend
echo "== pytest (M50 + yetki)"
/data/nanobaseai/bi/semantic-venv/bin/python -m pytest -q -p no:cacheprovider semantic_layer/tests/test_model_quality.py \
  semantic_layer/tests/test_access.py 2>&1 | tail -25
cd $W/src
echo "== betik sözdizimi"
bash -n scripts/server/model-quality-run.sh && bash -n scripts/server/model-quality-version.sh && echo "betikler tamam"
python3 -m py_compile tests/text2sql/resolver-gate.py tests/text2sql/answer-gate.py tests/text2sql/mq_report.py && echo "kapı betikleri tamam"
ln -sfn /data/nanobaseai/bi/frontend/node_modules node_modules
echo "== tsc"
timeout 900 npx tsc -b 2>&1 | tail -30; echo "tsc çıkış=${PIPESTATUS[0]}"
echo "== vitest"
timeout 900 npx vitest run 2>&1 | tail -12
echo "== build"
VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas timeout 1200 npx vite build --outDir $W/dist 2>&1 | tail -6
