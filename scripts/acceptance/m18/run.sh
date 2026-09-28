#!/bin/sh
# M18 kabul turu — test sunucusunda, köprünün kaynak ağacında (Mac'te koşulmaz).
#
#   cd <köprü kaynağı> && M18_COOKIE='timas_session=…' AY=2026-11 sh scripts/acceptance/m18/run.sh
#
# 1) Birim/kural testleri (SQLite, yapay veri; ürün doğruluğu kanıtı DEĞİLDİR, ayrı raporlanır).
# 2) Canlı kabul: gerçek CRM .28 + Logo .155, çalışan köprüye karşı, doğrudan SQL referanslarıyla (accept.py).
#    WRITE=1 verilirse ay planı yoksa taslak kurulur ve onay kuralı denenir.
# 3) Temizlik: kabulün kurduğu plan ve ilk kez açılan föy satırları + değişiklik kaydı silinir (cleanup.py). timasai
#    oturum satırı giriş servisinde ayrıca silinir (kullanıcı belleği «test-login-as-timasai»).
set -eu
cd "$(dirname "$0")/../../../backend"
set -a && . /etc/nanobase/semantic-bridge.env && set +a
: "${M18_COOKIE:?timasai kısa ömürlü oturum çerezi gerekli}"
: "${AY:?denetlenecek ay (YYYY-AA) gerekli}"
out="${OUT:-/tmp/claude-m18-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$out"

python3 -m pytest -q semantic_layer/tests/test_marketing_monthly.py semantic_layer/tests/test_marketing.py \
  semantic_layer/tests/test_access.py | tee "$out/pytest.txt"

status=0
M18_STATE="$out/state.json" python3 ../scripts/acceptance/m18/accept.py --ay "$AY" ${WRITE:+--write} \
  > "$out/kabul.json" || status=$?
M18_STATE="$out/state.json" python3 ../scripts/acceptance/m18/cleanup.py --state "$out/state.json" | tee "$out/temizlik.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d['ozet'], ensure_ascii=False))" "$out/kabul.json"
echo "kanıt: $out"
exit $status
