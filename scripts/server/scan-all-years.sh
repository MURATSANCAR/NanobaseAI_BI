#!/usr/bin/env bash
# Catalogue every year this database holds, not just the two that were in scope.
#
# TİMAŞ keeps a fiscal year per Logo firm code, and the deployment was reading two of them:
#
#   015 / 105  2015   (the same year twice)      171  2017      201  2020
#   016 / 115  2016   (the same year twice)      181  2018      211  2021-2025   <- scanned
#                                                191  2019      411  2026        <- scanned
#
# So a question about 2019 had nothing to land on. This widens the scope to all of them and profiles
# them; `periods.tables_for` then picks the year a question asks for, unions across a boundary, and
# reads one copy where a year is held twice.
#
# It is a full profile of about ten times the tables previously catalogued: expect it to take a
# while, and expect it to read the customer's database. It changes the catalog, so it takes a backup
# first and can be undone from that.
#
#   ssh nanobase-direct
#   cd /data/nanobaseai/bi/frontend && ./scripts/server/scan-all-years.sh [--dry-run]
set -euo pipefail

ROOT=/data/nanobaseai/bi/frontend
VENV=/data/nanobaseai/bi/semantic-venv/bin/python
ENVF=/etc/nanobase/semantic-bridge.env
DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

# Every Logo firm code this database declares. Read from L_CAPIFIRM on 2026-09-07; if a new fiscal
# year is opened, its code is added here and the scan re-run.
FIRMS="015 016 105 115 171 181 191 201 211 411"

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

cd "$ROOT/backend"
set -a; sudo cat "$ENVF" > /tmp/semantic.env; . /tmp/semantic.env; set +a
export PYTHONPATH=.

LIKE=""
for f in $FIRMS; do LIKE="${LIKE:+$LIKE,}LG_${f}_%"; done
LIKE="$LIKE,L_%"            # the database-wide tables (currencies, cities, firm definitions)
export SEMANTIC_TABLE_LIKE="$LIKE"
# No ceiling on how many tables are catalogued: which years exist is the database's answer, not a
# number chosen here. The deep-probe phase is bounded by wall clock instead (SEMANTIC_DEEP_BUDGET_SEC).
unset SEMANTIC_MAX_TABLES || true

echo "kapsam: $SEMANTIC_TABLE_LIKE"
if [[ $DRY -eq 1 ]]; then
  echo "(kuru çalışma — profil çıkarılmadı)"
  exit 0
fi

log "katalog yedeği"
D=$(echo "${SEMANTIC_STORE_DSN:-$NANOBASE_META_DSN}" | sed 's#postgresql+psycopg2://#postgresql://#;s#postgresql+psycopg://#postgresql://#')
pg_dump "$D" -t sl_schema_profile -f "/data/nanobaseai/bi/backups/sl_profiles-$(date +%Y%m%d-%H%M%S).sql"

log "profil — bütün yıllar"
"$VENV" -m semantic_layer.cli profile

log "sözlükten anlamları taşı"
"$VENV" scripts/enrich_catalog_from_dictionary.py --apply
"$VENV" scripts/derive_column_meanings.py --apply
"$VENV" scripts/describe_undocumented_tables.py --apply

log "köprüyü tazele"
curl -s -X POST http://127.0.0.1:8795/api/v1/semantic/reload >/dev/null
"$VENV" -m semantic_layer.cli status | head -20

cat <<'NOTE'

Sonraki adım: yıl başına kaç profil çıktığını doğrulayın. 2015 ve 2016 iki kez tutuluyor;
periods.tables_for kopyalardan birini okur ve hangisini atladığını söyler. Hangi kopyanın asıl
olduğu bir iş kararıdır — muhasebe onaylamalı.
NOTE
