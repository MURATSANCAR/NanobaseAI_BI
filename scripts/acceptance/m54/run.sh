#!/bin/sh
# M54 kabul turu — test sunucusunda, köprünün kaynak ağacında (Mac'te koşulmaz).
#
#   cd <köprü kaynağı> && M54_COOKIE='timas_session=…' PERIOD_START=2026-01-01 PERIOD_END=2026-06-30 \
#     [APPROVE_SAMPLE=5] sh scripts/acceptance/m54/run.sh
#
# 1) Birim/kural testleri (SQLite, yapay veri; ürün doğruluğu kanıtı DEĞİLDİR, ayrı raporlanır).
# 2) Canlı kabul: gerçek CRM .28 + Logo, çalışan köprüye karşı, doğrudan SQL referanslarıyla (accept.py). Test koşusu açar.
# 3) Temizlik: kabulün açtığı koşu, satırlar, (onay denendiyse) M6 hakedişleri ve portala alınan sözleşmeler silinir
#    (cleanup.py). timasai oturum satırı giriş servisinde ayrıca silinir (kullanıcı belleği «test-login-as-timasai»).
set -eu
cd "$(dirname "$0")/../../../backend"
set -a && . /etc/nanobase/semantic-bridge.env && set +a
: "${M54_COOKIE:?timasai kısa ömürlü oturum çerezi gerekli}"
: "${PERIOD_START:?dönem başı gerekli (ayın ilk günü)}"
: "${PERIOD_END:?dönem sonu gerekli (ayın son günü)}"
out="${OUT:-/tmp/claude-m54-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$out"

python3 -m pytest -q semantic_layer/tests/test_royalty.py semantic_layer/tests/test_contracts.py \
  semantic_layer/tests/test_access.py | tee "$out/pytest.txt"

status=0
M54_STATE="$out/state.json" python3 ../scripts/acceptance/m54/accept.py --period-start "$PERIOD_START" --period-end "$PERIOD_END" \
  --approve-sample "${APPROVE_SAMPLE:-0}" > "$out/kabul.json" || status=$?
M54_STATE="$out/state.json" python3 ../scripts/acceptance/m54/cleanup.py --state "$out/state.json" | tee "$out/temizlik.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d.get('ozet', d), ensure_ascii=False))" "$out/kabul.json"
echo "kanıt: $out"
exit $status
