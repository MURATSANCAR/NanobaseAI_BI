#!/usr/bin/env bash
# Forecasting V1 plan Faz 0.3/0.4 — apply branch_city view column + 48-month synthetic
# history to the live demo bi_reporting DB. Additive + idempotent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
PGHOST="${REPORTING_HOST:-127.0.0.1}"; PGPORT="${REPORTING_PORT:-5435}"
ADMIN_PW="$(tr -d '\n\r' < "${SECRETS}/reporting-admin.password")"
log() { printf '[apply-forecast-seed] %s\n' "$*"; }
export PGPASSWORD="$ADMIN_PW"
run() { psql -h "$PGHOST" -p "$PGPORT" -U bi_reporting_admin -d bi_reporting -v ON_ERROR_STOP=1 "$@"; }
log "view: v_sales_revenue_lines (+branch_city)"
run -f "${ROOT}/infra/sql/09-sales-revenue-lines-view.sql"
run -c "GRANT SELECT ON analytics.v_sales_revenue_lines, public.v_sales_revenue_lines TO bi_reporting_ro;"
log "seed: 48-month synthetic history"
run -f "${ROOT}/infra/sql/10-forecast-history-seed.sql"
run -c "SELECT date_trunc('month', order_date)::date AS month, branch_city, round(sum(line_total)) AS revenue
        FROM analytics.v_sales_revenue_lines WHERE status='completed'
        GROUP BY 1,2 ORDER BY 1 DESC, 2 LIMIT 9;"
run -c "SELECT count(*) AS orders, min(order_date), max(order_date) FROM analytics.sales_orders;"
log "done — no service restart needed (view column is additive, allowlist unchanged)"
