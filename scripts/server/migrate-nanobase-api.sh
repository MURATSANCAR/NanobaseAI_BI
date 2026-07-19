#!/usr/bin/env bash
# Run nanobase_api Alembic migrations against bi_meta.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${ROOT}/backend/.venv"
APP="${ROOT}/backend/nanobase_api"
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"

if [[ -z "${NANOBASE_META_DSN:-}" ]]; then
  META_PW="$(tr -d '\n\r' < "${SECRETS}/bi-meta-db.password")"
  META_PW_ENC="$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote_plus(sys.argv[1]))" "$META_PW")"
  export NANOBASE_META_DSN="postgresql+psycopg2://bi_meta:${META_PW_ENC}@127.0.0.1:5434/bi_meta"
fi

cd "$APP"
export PYTHONPATH="${ROOT}/backend"
"${VENV}/bin/alembic" -c alembic.ini upgrade head
echo "[migrate] nanobase_alembic_version head applied"
