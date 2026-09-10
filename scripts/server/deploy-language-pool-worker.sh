#!/usr/bin/env bash
# Install the product's incremental catalog maintenance worker, using its existing DB/LLM env.
set -euo pipefail
ROOT="${ROOT:-/data/nanobaseai/bi/frontend}"
VENV="${VENV:-/data/nanobaseai/bi/semantic-venv}"
ENV_FILE="${ENV_FILE:-/etc/nanobase/semantic-bridge.env}"
SERVICE_USER="${SERVICE_USER:-administrator}"
test -f "$ROOT/backend/scripts/maintain_language_pool.py"
test -f "$ENV_FILE"

sudo "$VENV/bin/python" - "$ENV_FILE" "$ROOT" "$SERVICE_USER" <<'PY'
import os, pwd, sys
from pathlib import Path
env, root, user = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
text = env.read_text()
if not any(line.startswith('SEMANTIC_LANGUAGE_POOL=') for line in text.splitlines()):
    folder = root / 'var'
    folder.mkdir(parents=True, exist_ok=True)
    owner = pwd.getpwnam(user)
    os.chown(folder, owner.pw_uid, owner.pw_gid)
    st = env.stat()
    tmp = env.with_name(env.name + '.language-pool-tmp')
    tmp.write_text(text.rstrip() + '\nSEMANTIC_LANGUAGE_POOL=' + str(folder / 'language-pool.json') + '\n')
    os.chmod(tmp, st.st_mode)
    os.chown(tmp, st.st_uid, st.st_gid)
    os.replace(tmp, env)
PY

sudo tee /etc/systemd/system/nanobase-language-pool.service >/dev/null <<EOF
[Unit]
Description=Incremental schema-bound language coverage for every catalog column
After=network-online.target nanobase-semantic-bridge.service
Wants=network-online.target

[Service]
Type=oneshot
User=${SERVICE_USER}
WorkingDirectory=${ROOT}/backend
EnvironmentFile=${ENV_FILE}
Environment=PYTHONPATH=${ROOT}/backend
Environment=SEMANTIC_LLM_MAX_WAIT_SEC=60
ExecStart=${VENV}/bin/python ${ROOT}/backend/scripts/maintain_language_pool.py --max-batches 24 --max-seconds 900
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
UMask=0077
TimeoutStartSec=2400
EOF

sudo tee /etc/systemd/system/nanobase-language-pool.timer >/dev/null <<'EOF'
[Unit]
Description=Resume language coverage and detect catalog description changes

[Timer]
OnBootSec=5min
OnUnitInactiveSec=2min
AccuracySec=30s
Unit=nanobase-language-pool.service

[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now nanobase-language-pool.timer
echo 'Catalog language maintenance timer installed; coverage is recorded beside the pool.'
