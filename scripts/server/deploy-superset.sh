#!/usr/bin/env bash
# Deploy Apache Superset analytics engine + wire nanobase_api BI_SUPERSET_*.
# Run on production host from repo root (or via ssh after rsync).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
COMPOSE_DIR="${ROOT}/infra/docker/superset"
ENV_API=/data/nanobaseai/bi/frontend/backend/nanobase_api.env
ENV_SS="${COMPOSE_DIR}/.env"
SECRETS=/data/nanobaseai/bi/secrets
DATA_ROOT=/data/nanobaseai/bi/infra

log() { printf '[deploy-superset] %s\n' "$*"; }
die() { printf '[deploy-superset] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -d "$COMPOSE_DIR" ]] || die "missing $COMPOSE_DIR — sync infra/docker/superset first"
command -v docker >/dev/null || die "docker required"
sudo docker compose version >/dev/null || die "sudo docker compose unavailable"
[[ -f "$ENV_API" ]] || die "missing $ENV_API"
DOCKER=(sudo docker)

mkdir -p "${DATA_ROOT}/superset-pg" "${DATA_ROOT}/superset-home" "$SECRETS"
chmod +x "${COMPOSE_DIR}/docker-entrypoint.sh"

# Prefer live stack secrets (prior compose) over regenerating.
EXISTING_ENV="${SUPERSET_EXISTING_ENV:-/data/nanobaseai-mobile/configs/superset-bi.env}"
GUEST_SECRET_FILE="${SECRETS}/superset-guest.jwt"
DB_PW_FILE="${SECRETS}/superset-db.password"
ADMIN_PW_FILE="${SECRETS}/superset-admin.password"
SS_SECRET_FILE="${SECRETS}/superset-secret.key"

_rand() { openssl rand -base64 48 | tr -d '\n/+=\r' | head -c 48; }

if [[ -f "$EXISTING_ENV" ]]; then
  log "Reusing credentials from $EXISTING_ENV"
  # shellcheck disable=SC1090
  set -a
  # shellcheck disable=SC1090
  source "$EXISTING_ENV"
  set +a
fi

[[ -n "${BI_SUPERSET_GUEST_SECRET:-}" ]] || {
  [[ -f "$GUEST_SECRET_FILE" ]] || { umask 077; _rand >"$GUEST_SECRET_FILE"; }
  BI_SUPERSET_GUEST_SECRET="$(tr -d '\n\r' <"$GUEST_SECRET_FILE")"
}
[[ -n "${BI_SUPERSET_PASSWORD:-}" ]] || {
  [[ -f "$ADMIN_PW_FILE" ]] || { umask 077; _rand >"$ADMIN_PW_FILE"; }
  BI_SUPERSET_PASSWORD="$(tr -d '\n\r' <"$ADMIN_PW_FILE")"
}
[[ -f "$DB_PW_FILE" ]] || { umask 077; _rand >"$DB_PW_FILE"; }
[[ -f "$SS_SECRET_FILE" ]] || { umask 077; _rand >"$SS_SECRET_FILE"; }
[[ -n "${SUPERSET_SECRET_KEY:-}" ]] || SUPERSET_SECRET_KEY="$(tr -d '\n\r' <"$SS_SECRET_FILE")"
[[ -n "${SUPERSET_DB_PASSWORD:-}" ]] || SUPERSET_DB_PASSWORD="$(tr -d '\n\r' <"$DB_PW_FILE")"

GUEST_SECRET="$BI_SUPERSET_GUEST_SECRET"
ADMIN_PW="$BI_SUPERSET_PASSWORD"
DB_PW="$SUPERSET_DB_PASSWORD"
SS_SECRET="$SUPERSET_SECRET_KEY"
ADMIN_USER="${BI_SUPERSET_USERNAME:-nanobase-bi-svc}"
GUEST_AUD="${BI_SUPERSET_GUEST_AUDIENCE:-${GUEST_TOKEN_JWT_AUDIENCE:-http://0.0.0.0:8080/}}"
PUBLIC_URL="${BI_SUPERSET_PUBLIC_URL:-https://portal.nanobase.ai:8443}"

umask 077
cat >"$ENV_SS" <<EOF
BI_SUPERSET_ENABLED=1
BI_SUPERSET_URL=http://127.0.0.1:8089
BI_SUPERSET_PUBLIC_URL=${PUBLIC_URL}
BI_SUPERSET_USERNAME=${ADMIN_USER}
BI_SUPERSET_PASSWORD=${ADMIN_PW}
BI_SUPERSET_GUEST_SECRET=${GUEST_SECRET}
BI_SUPERSET_GUEST_AUDIENCE=${GUEST_AUD}
BI_SUPERSET_GUEST_TTL_MIN=${BI_SUPERSET_GUEST_TTL_MIN:-30}
BI_SUPERSET_EMBED_DOMAINS=${BI_SUPERSET_EMBED_DOMAINS:-portal.nanobase.ai,bi.nanobase.ai,localhost,127.0.0.1}
SUPERSET_SECRET_KEY=${SS_SECRET}
SUPERSET_DB_PASSWORD=${DB_PW}
SUPERSET_DEFAULT_LOCALE=${SUPERSET_DEFAULT_LOCALE:-tr}
SUPERSET_CORS_ORIGINS=${SUPERSET_CORS_ORIGINS:-https://portal.nanobase.ai,https://bi.nanobase.ai,http://localhost:5173}
SUPERSET_DB_DATA=${DATA_ROOT}/superset-pg
SUPERSET_HOME=${DATA_ROOT}/superset-home
GUEST_TOKEN_JWT_AUDIENCE=${GUEST_AUD}
EOF
chmod 600 "$ENV_SS"

# If the analytics service is already healthy on :8089, skip recreate.
if curl -fsS -o /dev/null "http://127.0.0.1:8089/login/" 2>/dev/null; then
  log "Superset already up on :8089 — wiring API only"
  SKIP_COMPOSE=1
else
  SKIP_COMPOSE=0
fi

# --- merge into nanobase_api.env (preserve other keys) ---
log "Merging BI_SUPERSET_* into nanobase_api.env"
python3 - <<'PY' "$ENV_API" "$ENV_SS"
import sys
api_path, ss_path = sys.argv[1], sys.argv[2]
keys = {
    "BI_SUPERSET_ENABLED",
    "BI_SUPERSET_URL",
    "BI_SUPERSET_PUBLIC_URL",
    "BI_SUPERSET_USERNAME",
    "BI_SUPERSET_PASSWORD",
    "BI_SUPERSET_GUEST_SECRET",
    "BI_SUPERSET_GUEST_AUDIENCE",
    "BI_SUPERSET_GUEST_TTL_MIN",
    "BI_SUPERSET_EMBED_DOMAINS",
    "GUEST_TOKEN_JWT_AUDIENCE",
}
ss = {}
for line in open(ss_path, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    if k in keys:
        ss[k] = v
lines = []
seen = set()
for line in open(api_path, encoding="utf-8"):
    raw = line.rstrip("\n")
    if raw.strip().startswith("#") or "=" not in raw:
        lines.append(raw)
        continue
    k = raw.split("=", 1)[0]
    if k in ss:
        lines.append(f"{k}={ss[k]}")
        seen.add(k)
    else:
        lines.append(raw)
for k, v in ss.items():
    if k not in seen:
        lines.append(f"{k}={v}")
open(api_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("merged", sorted(ss))
PY
chmod 600 "$ENV_API"

# --- docker compose up (only if nothing on :8089) ---
if [[ "${SKIP_COMPOSE}" != "1" ]]; then
  log "Starting Superset stack on :8089"
  cd "$COMPOSE_DIR"
  "${DOCKER[@]}" compose --env-file .env pull || true
  "${DOCKER[@]}" compose --env-file .env up -d

  log "Waiting for Superset HTTP..."
  ok=0
  for i in $(seq 1 90); do
    if curl -fsS -o /dev/null "http://127.0.0.1:8089/health" 2>/dev/null \
      || curl -fsS -o /dev/null "http://127.0.0.1:8089/login/" 2>/dev/null; then
      ok=1
      break
    fi
    sleep 3
  done
  [[ "$ok" == "1" ]] || {
    log "WARN: Superset not healthy yet — check: sudo docker logs nanobase-superset"
    "${DOCKER[@]}" compose --env-file .env ps || true
  }
else
  log "Compose skipped — using existing nanobase-superset"
fi

# --- nginx analytics host (optional if certs exist) ---
NGINX_SRC="${ROOT}/deploy/nginx/portal-analytics-8443.conf"
NGINX_DST=/etc/nginx/sites-available/portal-analytics-8443.conf
if [[ -f "$NGINX_SRC" ]] && [[ -f /etc/letsencrypt/live/portal.nanobase.ai/fullchain.pem ]]; then
  log "Installing nginx portal-analytics-8443.conf"
  sudo cp "$NGINX_SRC" "$NGINX_DST"
  sudo ln -sfn "$NGINX_DST" /etc/nginx/sites-enabled/portal-analytics-8443.conf
  if sudo nginx -t 2>&1; then
    sudo systemctl reload nginx
    log "nginx reloaded (8443)"
  else
    log "WARN: nginx -t failed — leave 8443 for manual fix"
  fi
else
  log "SKIP nginx 8443 (missing cert or conf) — API still uses internal :8089"
fi

# --- restart API to pick env ---
log "Restarting nanobase-bi-api"
sudo systemctl restart nanobase-bi-api
sleep 3
curl -fsS http://127.0.0.1:8790/health | python3 -m json.tool
curl -fsS http://127.0.0.1:8790/api/v1/bi/analytics/status | python3 -m json.tool

log "Done. Admin user=${ADMIN_USER} password in ${ADMIN_PW_FILE}"
log "Verify: ${ROOT}/scripts/server/verify-superset.sh"
