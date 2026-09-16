#!/bin/sh
set -eu
# Read secrets inside psql; passwords do not appear in process arguments or logs.
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\set owner_password `cat /run/secrets/db_owner`
\set app_password `cat /run/secrets/db_app`
CREATE ROLE editor_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'owner_password';
CREATE ROLE editor_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
REVOKE ALL ON DATABASE editor FROM PUBLIC;
GRANT CONNECT ON DATABASE editor TO editor_owner, editor_app;
GRANT CREATE ON DATABASE editor TO editor_owner;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA editor AUTHORIZATION editor_owner;
CREATE SCHEMA checkpoints AUTHORIZATION editor_owner;
GRANT USAGE ON SCHEMA editor TO editor_app;
ALTER ROLE editor_app SET statement_timeout = '10s';
ALTER ROLE editor_app SET idle_in_transaction_session_timeout = '15s';
SQL
