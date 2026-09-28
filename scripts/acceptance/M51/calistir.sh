#!/usr/bin/env bash
# M51 kabul: test sunucusunda (nanobase-direct), main'den kurulmuş köprüyle. Tek ControlMaster bağlantısı üzerinden koşturulur.
#   KAYNAK=<git archive main açılmış dizin> OTURUM=/tmp/claude-<oturum> TIMAS_COOKIE='timas_session=…' \
#     bash scripts/acceptance/M51/calistir.sh
# Adımlar: 1) birim testleri (sunucuda)  2) masa referansı (MariaDB)  3) kabul.py  4) temizlik.py
set -euo pipefail
KAYNAK="${KAYNAK:?kaynak dizini}"
OTURUM="${OTURUM:?oturum klasörü}"
DESTEK_DB="${DESTEK_DB_CONTAINER:-nanobase-destek-db-1}"   # ölçülecek: compose'taki MariaDB konteynerinin adı
mkdir -p "$OTURUM"
BASLA="$(date -Iseconds)"
set -a; . /etc/nanobase/semantic-bridge.env; set +a
cd "$KAYNAK/backend"

echo "== 1. birim testleri"
python3 -m pytest -q semantic_layer/tests/test_support.py

echo "== 2. masa referansı"
if docker ps --format '{{.Names}}' | grep -qx "$DESTEK_DB"; then
  PW="$(grep -E '^DB_ROOT_PASSWORD=' /data/nanobaseai/destek/.env | cut -d= -f2-)"
  DBN="$(docker exec "$DESTEK_DB" mariadb -uroot -p"$PW" -N -e "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME LIKE '\_%' LIMIT 1")"
  sql() { docker exec "$DESTEK_DB" mariadb -uroot -p"$PW" -N "$DBN" -e "$1"; }
  W="opening_date BETWEEN CURDATE() - INTERVAL 29 DAY AND CURDATE()"
  python3 - "$OTURUM/m51-destek-ref.json" \
    "$(sql "SELECT COUNT(*) FROM \`tabHD Ticket\` WHERE $W")" \
    "$(sql "SELECT COUNT(*) FROM \`tabHD Ticket\` WHERE IFNULL(status_category,'') <> 'Resolved'")" \
    "$(sql "SELECT TIMESTAMPDIFF(SECOND, TIMESTAMP(opening_date, opening_time), first_responded_on)/60 FROM \`tabHD Ticket\` WHERE $W AND first_responded_on IS NOT NULL AND first_responded_on >= TIMESTAMP(opening_date, opening_time)" | tr '\n' ' ')" \
    "$(sql "SELECT feedback_rating FROM \`tabHD Ticket\` WHERE $W AND feedback_rating > 0" | tr '\n' ' ')" <<'PY'
import json, sys
out, opened, open_, fr, rt = sys.argv[1:6]
json.dump({"opened": int(opened), "open": int(open_), "first_minutes": [float(x) for x in fr.split()],
           "ratings": [float(x) for x in rt.split()]}, open(out, "w"))
PY
else
  echo "masa veritabanı konteyneri ($DESTEK_DB) yok; K5 DOĞRULANAMADI olarak kalır"
fi

echo "== 3. kabul"
set +e
BRIDGE_URL=http://127.0.0.1:8795 python3 ../scripts/acceptance/M51/kabul.py --out "$OTURUM/m51-kabul.json" \
  --destek-ref "$OTURUM/m51-destek-ref.json" --yazma
SONUC=$?
set -e

echo "== 4. temizlik"
python3 ../scripts/acceptance/M51/temizlik.py --actor timasai --since "$BASLA"
exit $SONUC
