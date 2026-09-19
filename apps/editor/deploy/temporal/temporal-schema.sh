#!/bin/sh
# Creates / migrates the two Temporal databases in the editor's own Postgres.
# Idempotent: create ignores "already exists", update-schema only applies new versions.
set -eu
T="temporal-sql-tool --plugin postgres12 --ep editor-postgres -p 5432 -u temporal --pw ${TEMPORAL_DB_PASSWORD}"
S=/etc/temporal/schema/postgresql/v12
for db in temporal temporal_visibility; do
  $T --db "$db" create 2>/dev/null || true
done
$T --db temporal setup-schema -v 0.0 2>/dev/null || true
$T --db temporal update-schema -d "$S/temporal/versioned"
$T --db temporal_visibility setup-schema -v 0.0 2>/dev/null || true
$T --db temporal_visibility update-schema -d "$S/visibility/versioned"
echo "temporal schema ok"
