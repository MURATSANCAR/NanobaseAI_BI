#!/bin/sh
# M15 kabul turu — test sunucusunda, köprünün kaynak ağacında (Mac'te koşulmaz).
#
#   cd <köprü kaynağı> && M15_COOKIE='timas_session=…' STOK=<yeni kitap stok kodu> sh scripts/acceptance/m15/run.sh
#
# 1) Birim/kural testleri (SQLite, yapay veri; ürün doğruluğu kanıtı DEĞİLDİR, ayrı raporlanır).
# 2) Canlı kabul: gerçek CRM .28 + Logo .155, çalışan köprüye karşı, doğrudan SQL referanslarıyla (accept.py).
# 3) Temizlik: kabulün bıraktığı plan/karne satırları ve değişiklik kaydı silinir (cleanup.py). timasai oturum satırı
#    giriş servisinde ayrıca silinir (kullanıcı belleği «test-login-as-timasai»).
set -eu
cd "$(dirname "$0")/../../../backend"
set -a && . /etc/nanobase/semantic-bridge.env && set +a
: "${M15_COOKIE:?timasai kısa ömürlü oturum çerezi gerekli}"
: "${STOK:?karnesi denetlenecek yeni kitap stok kodu gerekli}"
out="${OUT:-/tmp/claude-m15-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$out"

python3 -m pytest -q semantic_layer/tests/test_marketing.py semantic_layer/tests/test_access.py \
  semantic_layer/tests/test_budget.py | tee "$out/pytest.txt"

status=0
M15_STATE="$out/state.json" python3 ../scripts/acceptance/m15/accept.py --stok "$STOK" ${WRITE:+--write} \
  > "$out/kabul.json" || status=$?
M15_STATE="$out/state.json" python3 ../scripts/acceptance/m15/cleanup.py --state "$out/state.json" | tee "$out/temizlik.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d['ozet'], ensure_ascii=False))" "$out/kabul.json"
echo "kanıt: $out"
exit $status
