#!/usr/bin/env bash
# Apply rich reporting schema + refresh RO grants on live bi_reporting.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SECRETS=/data/nanobaseai/bi/secrets
SQL="${ROOT}/infra/sql/08-reporting-rich-schema.sql"
ADMIN_PW="$(tr -d '\n\r' < "${SECRETS}/reporting-admin.password")"

log() { printf '[apply-rich-schema] %s\n' "$*"; }
[[ -f "$SQL" ]] || { echo "missing $SQL"; exit 1; }

export PGPASSWORD="$ADMIN_PW"
log "Applying $SQL"
psql -h 127.0.0.1 -p 5435 -U bi_reporting_admin -d bi_reporting -v ON_ERROR_STOP=1 -f "$SQL"
psql -h 127.0.0.1 -p 5435 -U bi_reporting_admin -d bi_reporting -c \
  "SELECT 'invoices' AS t, count(*) FROM analytics.invoices
   UNION ALL SELECT 'payments', count(*) FROM analytics.payments
   UNION ALL SELECT 'sales_orders', count(*) FROM analytics.sales_orders;"
log "Done — restart query-gateway if allowlist updated"
