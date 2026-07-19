#!/usr/bin/env bash
# Faz 7: apply verified-SQL DDL + seed semantic catalog on bi_meta.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${ROOT}/backend/.venv"
SECRETS=/data/nanobaseai/bi/secrets

log() { printf '[deploy-semantic] %s\n' "$*"; }
die() { printf '[deploy-semantic] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f "${SECRETS}/bi-meta-db.password" ]] || die "missing bi-meta password"
[[ -x "${VENV}/bin/python" ]] || die "missing venv at $VENV"

export SECRETS_ROOT="$SECRETS"
log "Seeding semantic catalog + verified SQL"
"${VENV}/bin/python" "${ROOT}/backend/scripts/seed_semantic_catalog.py"

log "Done"
