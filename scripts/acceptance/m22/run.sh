#!/bin/sh
# M22 kabul turu — test sunucusunda, köprünün kaynak ağacında (Mac'te koşulmaz).
#
#   cd <köprü kaynağı> && M22_COOKIE='timas_session=…' [MONTH=2026-10] [WRITE=1] [DRAFT=1] sh scripts/acceptance/m22/run.sh
#
# 1) Birim/kural testleri (SQLite, yapay veri; ürün doğruluğu kanıtı DEĞİLDİR, ayrı raporlanır).
# 2) Canlı kabul: gerçek CRM .28 + Logo, çalışan köprüye karşı, doğrudan SQL referanslarıyla (accept.py).
# 3) Temizlik: kabulün bıraktığı hesap/gönderi/içe aktarma satırları ve değişiklik kaydı silinir (cleanup.py). timasai
#    oturum satırı giriş servisinde ayrıca silinir (kullanıcı belleği «test-login-as-timasai»).
set -eu
cd "$(dirname "$0")/../../../backend"
set -a && . /etc/nanobase/semantic-bridge.env && set +a
: "${M22_COOKIE:?timasai kısa ömürlü oturum çerezi gerekli}"
out="${OUT:-/tmp/claude-m22-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$out"

python3 -m pytest -q semantic_layer/tests/test_social.py semantic_layer/tests/test_access.py \
  semantic_layer/tests/test_marketing.py | tee "$out/pytest.txt"

status=0
M22_STATE="$out/state.json" python3 ../scripts/acceptance/m22/accept.py ${MONTH:+--month "$MONTH"} ${WRITE:+--write} \
  ${DRAFT:+--draft} > "$out/kabul.json" || status=$?
python3 ../scripts/acceptance/m22/cleanup.py --state "$out/state.json" | tee "$out/temizlik.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d['ozet'], ensure_ascii=False))" "$out/kabul.json"
echo "kanıt: $out"
exit $status
