#!/usr/bin/env bash
# M48 Sistem durumu — test sunucusunda kabul sırası (main'e merge + tam kurulumdan SONRA). Hiçbir servis yeniden
# başlatılmaz; zamanlayıcı yalnız kurulur ve ilk tur elle koşturulur (bellek run-it-before-it-runs-itself).
#
#   bash scripts/acceptance/M48/calistir.sh <kaynak-kökü> <oturum-klasörü>   # örn. /data/nanobaseai/bi/frontend /tmp/claude-XYZ
set -euo pipefail
SRC="${1:?kaynak kökü}"
OUT="${2:?oturum klasörü}"
mkdir -p "$OUT"
set +u -a; . /etc/nanobase/semantic-bridge.env; set -u +a
BEGIN="$(date --iso-8601=seconds)"

echo "== 1. birim testleri (köprünün sanal ortamı; yapay veri yalnız kural sınar)"
( cd "$SRC/backend" && python3 -m pytest -q semantic_layer/tests/test_it_ops.py semantic_layer/tests/test_access.py )

echo "== 2. zamanlayıcı birimleri (kurulur, ilk tur elle)"
sudo install -m 0644 "$SRC/scripts/server/timas-itops.service" "$SRC/scripts/server/timas-itops.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start timas-itops.service
journalctl -u timas-itops.service -n 5 --no-pager
sudo systemctl enable --now timas-itops.timer

echo "== 3. doğrudan SQL karşılaştırmaları"
( cd "$SRC/backend" && python3 ../scripts/acceptance/M48/kabul.py --out "$OUT/m48-kabul.json" --sha "${CODE_SHA:-}" )
echo "API ile: BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' … kabul.py --api --dene"
echo "Bitince: python3 ../scripts/acceptance/M48/temizlik.py --since '$BEGIN' --actor timasai  (ve timasai oturum satırı silinir)"
