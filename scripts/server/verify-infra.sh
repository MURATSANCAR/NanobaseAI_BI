#!/usr/bin/env bash
# Health checks for Faz-1 infra (server).
set -euo pipefail

SECRETS_DIR="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
fail=0
ok() { printf 'OK  %s\n' "$*"; }
bad() { printf 'FAIL %s\n' "$*"; fail=1; }

# Qdrant
if curl -fsS http://127.0.0.1:6333/collections >/dev/null; then
  ok "Qdrant :6333"
else
  bad "Qdrant :6333"
fi

# BGE-M3
if curl -fsS http://127.0.0.1:8083/health >/dev/null; then
  ok "BGE-M3 :8083 /health"
else
  bad "BGE-M3 :8083"
fi

# bi_meta
if sudo docker exec nanobase-bi-meta-db pg_isready -U bi_meta -d bi_meta >/dev/null 2>&1; then
  ok "bi_meta Postgres :5434"
else
  bad "bi_meta Postgres :5434"
fi

# reporting
if sudo docker exec nanobase-bi-reporting-db pg_isready -U bi_reporting_admin -d bi_reporting >/dev/null 2>&1; then
  ok "reporting Postgres :5435"
else
  bad "reporting Postgres :5435"
fi

# RO select + write denial
if [[ -f "${SECRETS_DIR}/reporting-ro.password" ]]; then
  RO_PW="$(tr -d '\n\r' < "${SECRETS_DIR}/reporting-ro.password")"
  rows="$(sudo docker exec -e PGPASSWORD="$RO_PW" nanobase-bi-reporting-db \
    psql -U bi_reporting_ro -d bi_reporting -Atc 'SELECT count(*) FROM analytics.customers;' 2>/dev/null || echo err)"
  if [[ "$rows" =~ ^[0-9]+$ ]] && [[ "$rows" -gt 0 ]]; then
    ok "RO SELECT analytics.customers (n=${rows})"
  else
    bad "RO SELECT analytics.customers"
  fi
  if sudo docker exec -e PGPASSWORD="$RO_PW" nanobase-bi-reporting-db \
    psql -U bi_reporting_ro -d bi_reporting -c "INSERT INTO analytics.customers(customer_name,country,segment) VALUES('x','TR','smb');" >/dev/null 2>&1; then
    bad "RO INSERT should be denied"
  else
    ok "RO INSERT denied"
  fi
else
  bad "missing reporting-ro.password"
fi

# Embedding auth smoke
API_KEY=""
if [[ -r /etc/nanobaseai/contract.env ]]; then
  # shellcheck disable=SC1091
  set -a; source /etc/nanobaseai/contract.env; set +a
  API_KEY="${CONTRACT_API_KEY:-}"
elif sudo test -f /etc/nanobaseai/contract.env; then
  API_KEY="$(sudo grep -E '^CONTRACT_API_KEY=' /etc/nanobaseai/contract.env | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
fi
API_KEY="${API_KEY:-${EMBEDDING_API_KEY:-}}"
if [[ -n "$API_KEY" ]]; then
  code="$(curl -sS -o /tmp/emb-verify.json -w '%{http_code}' \
    -H "Authorization: Bearer ${API_KEY}" \
    -H 'Content-Type: application/json' \
    -d '{"texts":["nanobase bi infra verify"]}' \
    http://127.0.0.1:8083/v1/embeddings || true)"
  if [[ "$code" == "200" ]]; then
    ok "BGE-M3 /v1/embeddings auth (${code})"
  else
    bad "BGE-M3 /v1/embeddings auth (http ${code})"
  fi
else
  bad "No CONTRACT_API_KEY for embedding auth check"
fi

exit "$fail"
