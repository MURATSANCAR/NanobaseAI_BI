#!/usr/bin/env bash
set -euo pipefail
umask 077
exec 9>/data/nanobaseai/bi/backups/language-pool-20260909/acceptance.lock
flock -n 9
if pgrep -f '^/data/nanobaseai/bi/semantic-venv/bin/python .*/enduser_live_10000.py' >/dev/null; then
  echo 'Another live corpus run is active'; exit 1
fi
set -a
source /etc/nanobase/semantic-bridge.env
set +a
export PYTHONPATH=/data/nanobaseai/bi/frontend/backend
/data/nanobaseai/bi/semantic-venv/bin/python /tmp/language-pool-release/snapshot.py before-final
/data/nanobaseai/bi/semantic-venv/bin/python /tmp/language-pool-release/scoped_acceptance.py
/data/nanobaseai/bi/semantic-venv/bin/python /tmp/language-pool-release/context_guards.py
/data/nanobaseai/bi/semantic-venv/bin/python /tmp/language-pool-release/feature_acceptance_final.py
/data/nanobaseai/bi/semantic-venv/bin/python /tmp/language-pool-release/lookup_acceptance_final.py
/data/nanobaseai/bi/semantic-venv/bin/python /tmp/language-pool-release/pool_check.py
exec bash /tmp/language-pool-release/run-100.sh
