#!/usr/bin/env bash
# Register Neon erp/sigorta as Query Gateway RO datasources (from connection.local.json).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${ROOT}/backend/.venv"
SECRETS=/data/nanobaseai/bi/secrets

log() { printf '[deploy-neon-ro] %s\n' "$*"; }
die() { printf '[deploy-neon-ro] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "${SECRETS}/connection.local.json" ]] || die "missing ${SECRETS}/connection.local.json"
[[ -x "${VENV}/bin/python" ]] || die "missing venv"

export SECRETS_ROOT="$SECRETS"
log "Building neon-ro.datasources.json + schema hints"
"${VENV}/bin/python" "${ROOT}/backend/scripts/build_neon_ro_map.py"

if [[ "${PROVISION_RO_ROLES:-1}" == "1" ]]; then
  log "Provisioning dedicated bi_*_ro roles"
  "${VENV}/bin/python" "${ROOT}/backend/scripts/provision_neon_ro_roles.py"
fi

log "Syncing bi_sources secret_ref/username from neon-ro map"
"${VENV}/bin/python" "${ROOT}/backend/scripts/sync_bi_sources_from_neon_ro.py"

sudo systemctl restart nanobase-query-gateway
sleep 2
curl -fsS http://127.0.0.1:8792/health | python3 -m json.tool
log "Done — run verify-neon-ro.sh / verify-e2e.sh"
