#!/bin/bash
# Zeki AI cevap kapısı — 2026-09-29 sınıf düzeltmeleri (docs/analiz/zeki-kapi-2026-09-29.md). Test sunucusunda koşar,
# Mac'te koşulmaz. Koordinatör adım adım koşar; çıktılar $W altına düşer. Sıra: main → test sunucusu → (ayrı iş) VM.
#
#   1            pytest (aday ağaç): semantic_layer/tests tamamı (önce bu dalın dosyası ve dokunduğu takımlar)
#   once         HIZLI KAPI ÖNCE — canlı köprü kurulumdan önce: resolver-gate set100 (okuma kaydı)
#   (kurulum)    yalnız değişen 7 dosya, md5 ile (bellek: deploy-only-changed-files), köprü yeniden yüklenir:
#                backend/semantic_layer/runtime/{critic,federated,compiler,resolver}.py
#                backend/semantic_bridge/{chat_portal,chat_scope,app}.py
#   sonra        HIZLI KAPI SONRA: resolver-gate yeniden, ÖNCE ile fark. Beklenen fark YALNIZ A044 (Q49) ve B064 (Q63).
#                Başka soru değişirse DUR: 1b (ayrık ölçü adı) ya da 2b (kırılım sözcüğü) yan etkisidir.
#   katalog-kuru kaydın adı kolonları (record_label) — aday listesi; etkinlik ve fuar gideri (Logo) --olc ölçümü; yazmaz
#   katalog-yaz  aynı betik --apply (liste okunduktan sonra; yanlış aday varsa EXCLUDE="terim,terim")
#   hedefli      answer-gate --only Q4,Q11,Q29,Q40,Q43,Q49,Q63,Q69 --repeat 3 (altın 09-29: Q29, Q63, Q69 güncel)
#   tam          answer-gate --repeat 3 --report (temel çizgi 52/11/4/2; SAĞLAM→BOZUK her geçiş bu dalın gerilemesi)
#   kalite       quality-gate (golden, SEMANTIC_TABLE_SELECTOR=off SEMANTIC_LLM=0) — recall düşerse DUR
#
# Kullanım: W=/tmp/claude-zeki-kapi SRC=$W/src LIVE=http://127.0.0.1:8795 ./calistir.sh <adım>
# Uzun koşu canlı köprünün yeniden başlatılmasında kopar (bellek: acceptance-side-bridge): tam kapıyı yan köprüde
# (LIVE=http://127.0.0.1:8798, --uid=administrator kopyası) koşmak güvenlidir.
set -u
W=${W:-/tmp/claude-zeki-kapi}
SRC=${SRC:-$W/src}
VENV=${VENV:-/data/nanobaseai/bi/semantic-venv/bin/python}
ENVF=${ENVF:-/etc/nanobase/semantic-bridge.env}
LIVE=${LIVE:-http://127.0.0.1:8795}
EXCLUDE=${EXCLUDE:-}
mkdir -p "$W"

run_env() {   # köprünün ortamıyla, aday ağaçtan
  sudo systemd-run --pipe --wait --collect -p User=administrator -p EnvironmentFile="$ENVF" \
    -E PYTHONPATH="$SRC/backend" -p WorkingDirectory="$SRC" "$@"
}

case "${1:-}" in
  1)
    echo "== ._ sayısı: $(find "$SRC" -name '._*' -type f -not -path '*/node_modules/*' | wc -l)"
    cd "$SRC/backend" && $VENV -m pytest -q -p no:cacheprovider semantic_layer/tests/test_zeki_kapi_0929.py \
      semantic_layer/tests/test_critic.py semantic_layer/tests/test_federated.py semantic_layer/tests/test_chat_portal.py \
      semantic_layer/tests/test_chat_scope.py semantic_layer/tests/test_runtime.py \
      semantic_layer/tests/test_cross_source_compile.py 2>&1 | tail -30
    echo "== semantic_layer/tests tamamı"
    $VENV -m pytest -q -p no:cacheprovider semantic_layer/tests 2>&1 | tail -15
    ;;
  once|sonra)
    # ÖNCE bugünkü okumayı temel çizgi olarak kaydeder (--record); SONRA ona karşı karşılaştırır (değişen varsa çıkış 1).
    tag=$1
    cd "$SRC"
    rec=(); [ "$tag" = once ] && rec=(--record)
    run_env $VENV tests/text2sql/resolver-gate.py tests/text2sql/set100.jsonl --baseline "$W/cozucu-temel.json" \
      ${rec[@]+"${rec[@]}"} --url "$LIVE" > "$W/cozucu-$tag.txt" 2>&1
    echo "== çözücü kapısı ($tag) çıkış=$?  → $W/cozucu-$tag.txt"; tail -12 "$W/cozucu-$tag.txt"
    ;;
  katalog-kuru|katalog-yaz)
    args=(); [ "$1" = katalog-yaz ] && args+=(--apply); [ -n "$EXCLUDE" ] && args+=(--exclude "$EXCLUDE")
    run_env $VENV - ${args[@]+"${args[@]}"} < "$SRC/scripts/catalog-authoring/2026-09-29-kayit-adi-kolonlari.py" | tee "$W/$1.txt"
    # etkinlik ve fuar gideri (Logo, yansıtma fişi hariç): kuruda --olc ile bu yıl (4.831.871,56) ve geçen yıl (≠ 0)
    eargs=(); [ "$1" = katalog-yaz ] && eargs+=(--apply) || eargs+=(--olc)
    run_env $VENV - "${eargs[@]}" < "$SRC/scripts/catalog-authoring/2026-09-29-etkinlik-fuar-gideri.py" | tee -a "$W/$1.txt"
    ;;
  hedefli)
    cd "$SRC"
    run_env $VENV tests/text2sql/answer-gate.py --only Q4,Q11,Q29,Q40,Q43,Q49,Q63,Q69 --repeat 3 --url "$LIVE" \
      --backend "$SRC/backend" --out "$W/hedefli.json" > "$W/hedefli.txt" 2>&1
    echo "== hedefli tam kapı çıkış=$?"; tail -25 "$W/hedefli.txt"
    ;;
  tam)
    cd "$SRC"
    run_env $VENV tests/text2sql/answer-gate.py --repeat 3 --url "$LIVE" --backend "$SRC/backend" \
      --out "$W/tam.json" --report "$LIVE" > "$W/tam.txt" 2>&1
    echo "== tam kapı çıkış=$?"; tail -3 "$W/tam.txt"
    ;;
  kalite)
    cd "$SRC"
    run_env -E SEMANTIC_TABLE_SELECTOR=off -E SEMANTIC_LLM=0 $VENV tests/text2sql/quality-gate.py > "$W/kalite.txt" 2>&1
    echo "== kalite kapısı çıkış=$?"; tail -12 "$W/kalite.txt"
    ;;
  *)
    echo "kullanım: $0 1|once|sonra|katalog-kuru|katalog-yaz|hedefli|tam|kalite"; exit 2 ;;
esac
