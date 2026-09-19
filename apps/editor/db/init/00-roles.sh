#!/bin/sh
# First boot of the editor's own Postgres: roles and databases.
# Ledger tables are created by migrations (editor.db.migrate) on worker start.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<SQL
CREATE ROLE editor_app LOGIN PASSWORD '${EDITOR_DB_PASSWORD}';
CREATE ROLE temporal LOGIN CREATEDB PASSWORD '${TEMPORAL_DB_PASSWORD}';
CREATE DATABASE editor OWNER editor_app;
SQL
