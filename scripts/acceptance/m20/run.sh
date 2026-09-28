#!/bin/sh
# M20 kabul turu — test sunucusunda, köprünün kaynak ağacında (Mac'te koşulmaz).
#
#   cd <köprü kaynağı> && M20_COOKIE='timas_session=…' [AY=2026-09] [WRITE=1] [RUN_DUE=1] sh scripts/acceptance/m20/run.sh
#
# 1) Birim/kural testleri (SQLite, yapay veri; ürün doğruluğu kanıtı DEĞİLDİR, ayrı raporlanır).
# 2) Canlı kabul: gerçek CRM .28, çalışan köprüye karşı, doğrudan SQL referanslarıyla (accept.py).
# 3) Temizlik: kabulün bıraktığı PR dosyası ve değişiklik kaydı silinir (cleanup.py). timasai oturum satırı giriş
#    servisinde ayrıca silinir (kullanıcı belleği «test-login-as-timasai»).
# RUN_DUE=1 run-due'yu da koşturur: takip günü geçmiş gönderim varsa hatırlatma e-postası gidebilir — alıcıları önce
# Yönetim → Pazarlama planları'ndan kontrol edin.
set -eu
cd "$(dirname "$0")/../../../backend"
set -a && . /etc/nanobase/semantic-bridge.env && set +a
: "${M20_COOKIE:?timasai kısa ömürlü oturum çerezi gerekli}"
out="${OUT:-/tmp/claude-m20-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$out"

python3 -m pytest -q semantic_layer/tests/test_pr.py semantic_layer/tests/test_access.py \
  semantic_layer/tests/test_marketing.py | tee "$out/pytest.txt"

status=0
M20_STATE="$out/state.json" python3 ../scripts/acceptance/m20/accept.py ${AY:+--ay "$AY"} ${WRITE:+--write} ${RUN_DUE:+--run-due} \
  > "$out/kabul.json" || status=$?
python3 ../scripts/acceptance/m20/cleanup.py --state "$out/state.json" | tee "$out/temizlik.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d['ozet'], ensure_ascii=False))" "$out/kabul.json"
echo "kanıt: $out"
exit $status
