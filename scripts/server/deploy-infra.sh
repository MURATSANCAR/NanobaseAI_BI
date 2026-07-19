#!/usr/bin/env bash
# Deploy Nanobase BI Faz-1 infra on the production server.
# Expected host: 38.247.162.28 — run as administrator with passwordless sudo for docker.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INFRA_DIR="${INFRA_ROOT:-/data/nanobaseai/bi/infra}"
SECRETS_DIR="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
COMPOSE_SRC="${ROOT}/infra/docker-compose.infra.yml"
SQL_SRC="${ROOT}/infra/sql"

log() { printf '[deploy-infra] %s\n' "$*"; }
die() { printf '[deploy-infra] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] && die "Do not run as root; use administrator + sudo docker"

command -v docker >/dev/null || die "docker not found"
sudo docker compose version >/dev/null || die "docker compose unavailable"

mkdir -p "${INFRA_DIR}/sql" "${INFRA_DIR}/reporting-pg" "${SECRETS_DIR}"
chmod 700 "${SECRETS_DIR}"

ensure_secret() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    log "Generating secret $(basename "$path")"
    openssl rand -base64 32 | tr -d '\n' > "$path"
    chmod 600 "$path"
  else
    log "Secret exists: $(basename "$path")"
  fi
}

ensure_secret "${SECRETS_DIR}/reporting-admin.password"
ensure_secret "${SECRETS_DIR}/reporting-ro.password"

# bi-meta password already managed separately
if [[ ! -f "${SECRETS_DIR}/bi-meta-db.password" ]]; then
  die "Missing ${SECRETS_DIR}/bi-meta-db.password (existing nanobase-bi-meta-db)"
fi

log "Syncing compose + SQL into ${INFRA_DIR}"
install -m 644 "${COMPOSE_SRC}" "${INFRA_DIR}/docker-compose.infra.yml"
install -m 644 "${SQL_SRC}/01-reporting-seed.sql" "${INFRA_DIR}/sql/01-reporting-seed.sql"
install -m 755 "${SQL_SRC}/02-reporting-ro-user.sh" "${INFRA_DIR}/sql/02-reporting-ro-user.sh"

# Ensure data dir ownership for postgres:16-alpine (uid 70)
if [[ -d "${INFRA_DIR}/reporting-pg" ]]; then
  sudo chown -R 70:70 "${INFRA_DIR}/reporting-pg" || true
fi

# Fix existing bi_meta data dir if needed
if [[ -d /data/nanobaseai/bi/postgres ]]; then
  owner="$(stat -c '%u' /data/nanobaseai/bi/postgres)"
  if [[ "$owner" != "70" ]]; then
    log "Fixing bi_meta data ownership (was uid ${owner} → 70)"
    sudo chown -R 70:70 /data/nanobaseai/bi/postgres
    sudo docker restart nanobase-bi-meta-db >/dev/null || true
  fi
fi

cd "${INFRA_DIR}"
log "Starting reporting Postgres"
sudo docker compose -f docker-compose.infra.yml up -d

log "Waiting for health"
for i in $(seq 1 40); do
  if sudo docker exec nanobase-bi-reporting-db pg_isready -U bi_reporting_admin -d bi_reporting >/dev/null 2>&1; then
    break
  fi
  sleep 1
  if [[ "$i" -eq 40 ]]; then
    sudo docker logs nanobase-bi-reporting-db --tail 50 >&2 || true
    die "reporting db not healthy"
  fi
done

# If volume already existed without RO role (re-init skipped), ensure role exists
ADMIN_PW="$(tr -d '\n\r' < "${SECRETS_DIR}/reporting-admin.password")"
RO_LITERAL="$(python3 -c "import pathlib; print(repr(pathlib.Path('${SECRETS_DIR}/reporting-ro.password').read_text().strip()))")"
sudo docker exec -e PGPASSWORD="$ADMIN_PW" nanobase-bi-reporting-db \
  psql -U bi_reporting_admin -d bi_reporting -v ON_ERROR_STOP=1 \
  -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='bi_reporting_ro') THEN CREATE ROLE bi_reporting_ro LOGIN; END IF; END \$\$;"
sudo docker exec -e PGPASSWORD="$ADMIN_PW" nanobase-bi-reporting-db \
  psql -U bi_reporting_admin -d bi_reporting -v ON_ERROR_STOP=1 \
  -c "ALTER ROLE bi_reporting_ro WITH LOGIN PASSWORD ${RO_LITERAL};"
sudo docker exec -e PGPASSWORD="$ADMIN_PW" nanobase-bi-reporting-db \
  psql -U bi_reporting_admin -d bi_reporting -v ON_ERROR_STOP=1 \
  -c "GRANT CONNECT ON DATABASE bi_reporting TO bi_reporting_ro;" \
  -c "GRANT USAGE ON SCHEMA analytics TO bi_reporting_ro;" \
  -c "GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO bi_reporting_ro;" \
  -c "ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO bi_reporting_ro;"

log "Verifying shared services"
curl -fsS "http://127.0.0.1:6333/collections" >/dev/null || die "Qdrant :6333 unreachable"
curl -fsS "http://127.0.0.1:8083/health" >/dev/null || die "BGE-M3 :8083 unreachable"
sudo docker exec nanobase-bi-meta-db pg_isready -U bi_meta -d bi_meta >/dev/null \
  || die "bi_meta :5434 unhealthy"

# Write connection hints (no passwords) for ops
cat > "${INFRA_DIR}/ENDPOINTS.md" <<EOF
# Nanobase BI infra endpoints (loopback)

| Service | Endpoint |
|---------|----------|
| Qdrant (shared) | http://127.0.0.1:6333 |
| BGE-M3 (shared) | http://127.0.0.1:8083 |
| bi_meta Postgres | 127.0.0.1:5434 / bi_meta / bi_meta |
| reporting Postgres | 127.0.0.1:5435 / bi_reporting |
| reporting RO role | bi_reporting_ro (SELECT on analytics.*) |
| Secrets | ${SECRETS_DIR}/reporting-*.password |

Compose: ${INFRA_DIR}/docker-compose.infra.yml
EOF

log "Done. See ${INFRA_DIR}/ENDPOINTS.md"
"${ROOT}/scripts/server/verify-infra.sh" || true
