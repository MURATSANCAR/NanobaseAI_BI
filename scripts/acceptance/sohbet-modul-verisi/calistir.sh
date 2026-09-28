#!/bin/bash
# Zeki AI sohbetine modül verisi (chat_portal, 2026-09-28) — test sunucusunda uygulama ve kabul. Mac'te koşulmaz.
# Koordinatör adım adım koşar; her adımın çıktısı $W altına düşer. Kurulum sırası: main → test sunucusu → (ayrı iş) VM.
#
#   0. Aday ağaç: git archive <sha> | tar -x -C $W/src   (._* sayısı 0 olmalı; adım 1 yazar)
#   1. pytest (Mac'te koşulmadı): chat_portal, chat_scope, yetki, veri güvenliği envanteri, yönetim ayarları
#   2. HIZLI KAPI — ÖNCE (canlı köprü :8795, kurulumdan önce):
#        a) kabul.py --scan              → portal kelimesi taşıyan altın sorular (bunlar artık sınıflandırıcıya uğrar)
#        b) resolver-gate.py set100.jsonl → çözücü okuması (bu iş çözücüye dokunmaz; SONRA fark 0 beklenir)
#        c) answer-gate.py --only <a'daki kimlikler> --repeat 3   (liste boşsa atlanır)
#        d) quality-gate.py (golden; SEMANTIC_TABLE_SELECTOR=off SEMANTIC_LLM=0)  — derleyiciye dokunulmadı, fark 0
#   3. Kurulum: yalnız değişen dosyalar (md5 ile), köprü yeniden yüklenir (bellek: deploy-only-changed-files):
#        backend/semantic_bridge/{chat_portal.py,chat_portal_areas.json,chat_topics.json,chat_scope.py,access.py,
#        admin.py,app.py}
#      Yönetim → Ayarlar: CHAT_CONNECTED_TOPICS doluysa yeni konular (pazarlama,dijital,eticaret,okur,destek,risk,
#      yonetim,isletim,editoryal) eklenmeli; boşsa kendiliğinden bağlı.
#   4. Katalog: kuru koşu → incele (dışarıda kalan kolonlar, bağlar, «tablosu olmayan alanlar») → --apply → --certify
#   5. HIZLI KAPI — SONRA: 2b, 2c, 2d yeniden; ÖNCE ile karşılaştır. Çözücü farkı ≠ 0 ya da tam kapıda bozulan varsa DUR.
#   6. kabul.py --references (portal DB ↔ doğrudan SQL R1–R10, yetki, satır kapsamı, katalogda kişisel kolon yok)
#   7. timasai kısa oturumu → kabul.py --live (gerçek model) → temizlik.py → oturum silinir
#   8. Sohbet kapsamı kabulü (scripts/acceptance/chat_scope) — kimlik/model reddi aynen; İK artık kendi kapalı metnini alır
#
# Kullanım: W=/tmp/claude-sohbet-modul SRC=$W/src ./calistir.sh <adım>   (adım: 1 | once | katalog-kuru | katalog-yaz |
#           katalog-onay | sonra | referans | canli)
set -u
W=${W:-/tmp/claude-sohbet-modul}
SRC=${SRC:-$W/src}
VENV=${VENV:-/data/nanobaseai/bi/semantic-venv/bin/python}
ENVF=${ENVF:-/etc/nanobase/semantic-bridge.env}
LIVE=${LIVE:-http://127.0.0.1:8795}
SIDE=${SIDE:-http://127.0.0.1:8798}
mkdir -p $W

run_env() {   # köprünün ortamıyla, aday ağaçtan
  sudo systemd-run --pipe --wait --collect -p User=administrator -p EnvironmentFile=$ENVF \
    -E PYTHONPATH=$SRC/backend -p WorkingDirectory=$SRC "$@"
}

case "${1:-}" in
  1)
    echo "== ._ sayısı: $(find $SRC -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
    cd $SRC/backend && $VENV -m pytest -q -p no:cacheprovider semantic_layer/tests/test_chat_portal.py \
      semantic_layer/tests/test_chat_scope.py semantic_layer/tests/test_access.py \
      semantic_layer/tests/test_access_data.py semantic_layer/tests/test_data_security.py 2>&1 | tail -30
    ;;
  once|sonra)
    tag=$1
    run_env $VENV $SRC/scripts/acceptance/sohbet-modul-verisi/kabul.py --scan --out $W/tarama-$tag.json | tail -3
    ONLY=$(python3 -c "import json;d=json.load(open('$W/tarama-$tag.json'))['scan'];print(','.join(d.get('answers-set100.json',[])))")
    echo "== portal kelimeli altın sorular: ${ONLY:-yok}"
    cd $SRC
    run_env $VENV tests/text2sql/resolver-gate.py tests/text2sql/set100.jsonl --url $LIVE > $W/cozucu-$tag.txt 2>&1
    echo "== çözücü kapısı ($tag) çıkış=$?  → $W/cozucu-$tag.txt"; tail -5 $W/cozucu-$tag.txt
    if [ -n "$ONLY" ]; then
      run_env $VENV tests/text2sql/answer-gate.py --only "$ONLY" --repeat 3 --url $LIVE --out $W/tam-$tag.json \
        > $W/tam-$tag.txt 2>&1
      echo "== tam kapı (--only) ($tag) çıkış=$?"; tail -8 $W/tam-$tag.txt
    fi
    run_env -E SEMANTIC_TABLE_SELECTOR=off -E SEMANTIC_LLM=0 $VENV tests/text2sql/quality-gate.py > $W/kalite-$tag.txt 2>&1
    echo "== kalite kapısı ($tag) çıkış=$?"; tail -12 $W/kalite-$tag.txt
    ;;
  katalog-kuru)
    run_env $VENV - --json $W/katalog-kuru.json < $SRC/scripts/catalog-authoring/2026-09-28-sohbet-portal-verisi.py | tee $W/katalog-kuru.txt
    ;;
  katalog-yaz)
    run_env $VENV - --apply --json $W/katalog-yaz.json < $SRC/scripts/catalog-authoring/2026-09-28-sohbet-portal-verisi.py | tail -20
    ;;
  katalog-onay)
    # Kuru koşuyu inceledikten sonra: hepsi ya da alan alan (ör. risk-uyum,kurul). Reddedilecek tablo varsa --reject.
    run_env $VENV - --certify "${ALANLAR:-all}" < $SRC/scripts/catalog-authoring/2026-09-28-sohbet-portal-verisi.py | tail -5
    ;;
  referans)
    run_env $VENV $SRC/scripts/acceptance/sohbet-modul-verisi/kabul.py --references --out $W/kabul-referans.json | tail -25
    ;;
  canli)
    # COOKIE: timasai'nin 15 dk'lık oturumu (bellek: test-login-as-timasai); iş bitince oturum satırı silinir.
    run_env -E COOKIE="${COOKIE:-}" -E BRIDGE=$SIDE $VENV $SRC/scripts/acceptance/sohbet-modul-verisi/kabul.py --live \
      --out $W/kabul-canli.json | tail -40
    run_env $VENV $SRC/scripts/acceptance/sohbet-modul-verisi/temizlik.py --evidence $W/kabul-canli.json
    ;;
  *)
    sed -n 2,26p "$0"; exit 2
    ;;
esac
