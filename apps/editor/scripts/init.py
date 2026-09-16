#!/usr/bin/env python3
"""Generate installation-specific secrets. Safe to repeat; never rotates existing keys."""
import os
from pathlib import Path
import secrets
import shutil

root = Path(__file__).resolve().parents[1]
folder = root / 'secrets'
folder.mkdir(mode=0o700, exist_ok=True)
os.chmod(folder, 0o700)
for name in ('db_admin', 'db_owner', 'db_app', 'api_token'):
    path = folder / name
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(fd, 'w') as stream:
            stream.write(secrets.token_hex(32) + '\n')
if not (root / '.env').exists():
    shutil.copyfile(root / '.env.example', root / '.env')
    os.chmod(root / '.env', 0o600)
print('Installation configuration ready; existing secrets preserved.')
