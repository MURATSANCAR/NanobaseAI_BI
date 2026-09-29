#!/bin/sh
# M21 kabul turu — test sunucusunda, köprünün kaynak ağacında (Mac'te koşulmaz).
#
#   cd <köprü kaynağı> && M21_COOKIE='timas_session=…' STOK=<e-ticarette satışı olan kitabın stok kodu> sh scripts/acceptance/M21/run.sh
#
# 1) Birim/kural testleri (SQLite, yapay veri; ürün doğruluğu kanıtı DEĞİLDİR, ayrı raporlanır).
# 2) Canlı kabul: gerçek CRM .28 + Logo .25, çalışan köprüye karşı, doğrudan SQL referanslarıyla (kabul.py).
#    İlk koşuda satış önbelleği boşsa REFRESH=1 verin (POST /api/v1/ads/refresh, bitmesi beklenir).
# 3) Temizlik: kabulün açtığı hesap/kampanya/dosya satırları ve değişiklik kaydı silinir (cleanup.py). timasai oturum
#    satırı giriş servisinde ayrıca silinir.
# Sonra: timas-ads.service bir kez elle koşturulur (ADS_ALERT_RECIPIENTS boşsa e-posta gitmez), sonra zamanlayıcı açılır.
set -eu
cd "$(dirname "$0")/../../../backend"
set -a && . /etc/nanobase/semantic-bridge.env && set +a
: "${M21_COOKIE:?timasai kısa ömürlü oturum çerezi gerekli}"
out="${OUT:-/tmp/claude-m21-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$out"

python3 -m pytest -q -p no:cacheprovider semantic_layer/tests/test_ads.py semantic_layer/tests/test_access.py \
  semantic_layer/tests/test_marketing.py | tee "$out/pytest.txt"

status=0
M21_STATE="$out/state.json" python3 ../scripts/acceptance/M21/kabul.py ${STOK:+--stok "$STOK" --write} ${REFRESH:+--refresh} \
  > "$out/kabul.json" || status=$?
python3 ../scripts/acceptance/M21/cleanup.py --state "$out/state.json" | tee "$out/temizlik.json"
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(json.dumps(d.get('ozet', d), ensure_ascii=False))" "$out/kabul.json"
echo "kanıt: $out"
exit $status
