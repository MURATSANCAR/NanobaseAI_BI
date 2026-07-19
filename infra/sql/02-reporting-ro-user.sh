#!/bin/bash
# Create read-only role for Query Gateway / DB-GPT.
# Password: /run/secrets/reporting_ro_password (preferred) or sibling password file.
set -euo pipefail

RO_PASSWORD_FILE=""
for candidate in \
  /run/secrets/reporting_ro_password \
  /docker-entrypoint-initdb.d/reporting-ro.password
do
  if [[ -f "$candidate" ]]; then
    RO_PASSWORD_FILE="$candidate"
    break
  fi
done

if [[ -z "$RO_PASSWORD_FILE" ]]; then
  echo "ERROR: RO password file missing" >&2
  exit 1
fi

RO_PASSWORD="$(tr -d '\n\r' < "$RO_PASSWORD_FILE")"
if [[ -z "$RO_PASSWORD" ]]; then
  echo "ERROR: RO password empty" >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bi_reporting_ro') THEN
    CREATE ROLE bi_reporting_ro LOGIN;
  END IF;
END
\$\$;
EOSQL

# Use psql variable binding to avoid shell metacharacter issues in password
psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  -v ro_pw="$RO_PASSWORD" \
  -c "ALTER ROLE bi_reporting_ro WITH LOGIN PASSWORD :'ro_pw';"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'EOSQL'
GRANT CONNECT ON DATABASE bi_reporting TO bi_reporting_ro;
GRANT USAGE ON SCHEMA analytics TO bi_reporting_ro;
GRANT USAGE ON SCHEMA public TO bi_reporting_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO bi_reporting_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bi_reporting_ro;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA analytics TO bi_reporting_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO bi_reporting_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO bi_reporting_ro;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA analytics FROM bi_reporting_ro;
ALTER ROLE bi_reporting_ro SET search_path TO public, analytics;
EOSQL

echo "bi_reporting_ro role ready"
