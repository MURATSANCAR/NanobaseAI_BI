#!/bin/sh
# M17 kabul turu — test sunucusunda, köprünün kaynak ağacında (Mac'te koşulmaz).
#
#   cd <köprü kaynağı> && M17_COOKIE='timas_session=…' [BUILD=1] [WRITE=1] [STOK=K1,K2] sh scripts/acceptance/m17/run.sh
#
# 1) Birim/kural testleri (SQLite, yapay veri; ürün doğruluğu kanıtı DEĞİLDİR, ayrı raporlanır).
# 2) BUILD=1: gece koşusu elle (liste + bileşenler + seri + kampanya etkisi; ilk koşuda geçmiş yıllar Logo'dan) — süresi
#    ölçülür ve günlüğe yazılır (kullanıcı belleği «zamanlı işi önce elle koştur»).
# 3) Canlı kabul: gerçek CRM .28 + Logo .25, çalışan köprüye karşı, doğrudan SQL referanslarıyla (accept.py).
# 4) Temizlik: kabulün açtığı plan ve değişiklik kaydı silinir (cleanup.py). timasai oturum satırı giriş servisinde
#    ayrıca silinir (kullanıcı belleği «test-login-as-timasai»).
set -eu
cd "$(dirname "$0")/../../../backend"
set -a && . /etc/nanobase/semantic-bridge.env && set +a
: "${M17_COOKIE:?timasai kısa ömürlü oturum çerezi gerekli}"
out="${OUT:-/tmp/claude-m17-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$out"

python3 -m pytest -q semantic_layer/tests/test_backlist.py semantic_layer/tests/test_marketing.py \
  semantic_layer/tests/test_access.py semantic_layer/tests/test_budget.py | tee "$out/pytest.txt"

if [ "${BUILD:-}" = "1" ]; then
  start=$(date +%s)
  curl -fsS -m 3590 -X POST -H "X-Semantic-Caller: ${SEMANTIC_CALLER_TOKEN}" \
    "http://127.0.0.1:8795/api/v1/marketing/backlist/run-due?adim=gece&force=true" > "$out/gece.json"
  echo "gece koşusu: $(( $(date +%s) - start )) sn" | tee "$out/sure.txt"
fi

status=0
M17_STATE="$out/state.json" python3 ../scripts/acceptance/m17/accept.py ${STOK:+--stok "$STOK"} ${WRITE:+--write} \
  > "$out/kabul.json" || status=$?
python3 ../scripts/acceptance/m17/cleanup.py --state "$out/state.json" | tee "$out/temizlik.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d.get('ozet'), ensure_ascii=False))" "$out/kabul.json"
echo "kanıt: $out"
exit $status
