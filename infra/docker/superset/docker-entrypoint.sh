#!/usr/bin/env bash
# Bootstrap Superset metadata DB + service account, then start webserver.
set -euo pipefail

echo "[nanobase-superset] waiting for db..."
python - <<'PY'
import os, time, sys
import sqlalchemy as sa
uri = os.environ["SQLALCHEMY_DATABASE_URI"]
for i in range(60):
    try:
        sa.create_engine(uri).connect().close()
        print("db ok")
        sys.exit(0)
    except Exception as e:
        print(f"db wait {i}: {e}")
        time.sleep(2)
sys.exit(1)
PY

superset db upgrade

ADMIN_USER="${ADMIN_USERNAME:-admin}"
ADMIN_PASS="${ADMIN_PASSWORD:-admin}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@nanobase.local}"

superset fab create-admin \
  --username "$ADMIN_USER" \
  --firstname Nanobase \
  --lastname BI \
  --email "$ADMIN_EMAIL" \
  --password "$ADMIN_PASS" || true

superset init

echo "[nanobase-superset] starting gunicorn on 8088"
exec /usr/bin/run-server.sh
