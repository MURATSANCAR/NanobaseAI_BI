#!/bin/sh
# M16 kabul turu — test sunucusunda, köprünün kaynak ağacında (Mac'te koşulmaz).
#
#   cd <köprü kaynağı> && M16_COOKIE='timas_session=…' STOK=<kod> YAYIN=<YYYY-AA-GG> sh scripts/acceptance/m16/run.sh
#
# 1) Birim/kural testleri (SQLite, yapay veri; ürün doğruluğu kanıtı DEĞİLDİR, ayrı raporlanır).
# 2) Canlı kabul: gerçek CRM .28 + Logo .155, çalışan köprüye karşı, doğrudan SQL referanslarıyla (accept.py) —
#    yakın geçmişte yayımlanmış bir yeni kitapta «geriye dönük lansman».
# 3) Temizlik: kabul planı, lansman ve bütün satırları, değişiklik kaydı, yeni emsal önbelleği silinir (cleanup.py).
#    timasai oturum satırı giriş servisinde ayrıca silinir (kullanıcı belleği «test-login-as-timasai»).
set -eu
cd "$(dirname "$0")/../../../backend"
set -a && . /etc/nanobase/semantic-bridge.env && set +a
: "${M16_COOKIE:?timasai kısa ömürlü oturum çerezi gerekli}"
: "${STOK:?kabul kitabının stok kodu gerekli}"
: "${YAYIN:?kabul kitabının yayın günü gerekli (YYYY-AA-GG)}"
out="${OUT:-/tmp/claude-m16-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$out"

python3 -m pytest -q semantic_layer/tests/test_marketing_launch.py semantic_layer/tests/test_marketing.py \
  semantic_layer/tests/test_access.py | tee "$out/pytest.txt"

status=0
M16_STATE="$out/state.json" python3 ../scripts/acceptance/m16/accept.py --stok "$STOK" --yayin "$YAYIN" \
  > "$out/kabul.json" || status=$?
python3 ../scripts/acceptance/m16/cleanup.py --state "$out/state.json" | tee "$out/temizlik.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d['ozet'], ensure_ascii=False))" "$out/kabul.json"
echo "kanıt: $out"
exit $status
