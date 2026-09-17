#!/usr/bin/env python3
"""Migrate one authorized systemd semantic service; never print credentials."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

import sqlalchemy as sa

p = argparse.ArgumentParser()
p.add_argument('--service', required=True)
p.add_argument('--env-file', required=True)
p.add_argument('--retire-file', action='append', default=[])
p.add_argument('--base', required=True)
p.add_argument('--model', required=True)
p.add_argument('--backup-root', default='/root/llm-migration-backups')
a = p.parse_args()
os.umask(0o077)
with urllib.request.urlopen(a.base.rstrip('/') + '/models', timeout=20) as response:
    models = json.load(response)
if a.model not in {m['id'] for m in models['data']}:
    raise SystemExit('EXPECTED_LOCAL_MODEL_NOT_READY')
pid = subprocess.check_output(['systemctl', 'show', a.service, '-p', 'MainPID', '--value'], text=True).strip()
env = dict(item.split('=', 1) for item in Path('/proc', pid, 'environ').read_bytes().decode().split('\0') if '=' in item)
dsn = env.get('SEMANTIC_STORE_DSN') or env.get('NANOBASE_META_DSN')
if not dsn:
    raise SystemExit('EXPLICIT_SEMANTIC_STORE_REQUIRED')
engine = sa.create_engine(dsn)
backup = Path(a.backup_root) / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
backup.mkdir(parents=True, mode=0o700)
updates = {'OPENAI_API_BASE': a.base.rstrip('/'), 'LLM_MODEL_NAME': a.model,
           'OPENAI_API_KEY': '', 'SEMANTIC_SELECTOR_BASE': a.base.rstrip('/'),
           'SEMANTIC_SELECTOR_MODEL': a.model,
           'LLM_EXTRA_BODY_JSON': '{"chat_template_kwargs":{"enable_thinking":false}}'}
paths = [Path(a.env_file), *(Path(x) for x in a.retire_file)]
for index, path in enumerate(paths):
    if path.exists():
        shutil.copy2(path, backup / (str(index) + '-' + path.name))
        (backup / (str(index) + '-' + path.name)).chmod(0o600)
with engine.begin() as db:
    rows = db.execute(sa.text('SELECT key,value,updated_by,updated_at FROM semantic_settings')).mappings().all()
    selected = [dict(row) for row in rows if row['key'] in updates or row['key'].startswith('NVIDIA_')]
    (backup / 'settings.json').write_text(json.dumps(selected, default=str))
    for row in selected:
        if row['key'].startswith('NVIDIA_'):
            db.execute(sa.text('DELETE FROM semantic_settings WHERE key=:key'), {'key': row['key']})
        else:
            db.execute(sa.text('UPDATE semantic_settings SET value=:value,updated_by=:actor,updated_at=CURRENT_TIMESTAMP WHERE key=:key'),
                       {'value': updates[row['key']], 'actor': 'authorized-local-llm-migration', 'key': row['key']})
path = Path(a.env_file)
lines = []
for line in path.read_text().splitlines():
    key = line.partition('=')[0].strip()
    if key in updates or key.startswith('NVIDIA_') or ('nvidia' in line.lower() and line.lstrip().startswith('#')):
        continue
    lines.append(line)
lines.extend(key + '=' + value for key, value in updates.items())
temporary = path.with_name(path.name + '.migration-tmp')
temporary.write_text('\n'.join(lines) + '\n')
temporary.chmod(path.stat().st_mode & 0o777)
os.chown(temporary, path.stat().st_uid, path.stat().st_gid)
temporary.replace(path)
for path in paths[1:]:
    path.unlink(missing_ok=True)
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'restart', a.service], check=True)
new_pid = subprocess.check_output(['systemctl', 'show', a.service, '-p', 'MainPID', '--value'], text=True).strip()
actual = dict(item.split('=', 1) for item in Path('/proc', new_pid, 'environ').read_bytes().decode().split('\0') if '=' in item)
assert actual.get('OPENAI_API_BASE') == updates['OPENAI_API_BASE']
assert actual.get('LLM_MODEL_NAME') == a.model
assert not any(key.startswith('NVIDIA_') for key in actual)
assert not actual.get('OPENAI_API_KEY')
print(json.dumps({'service': a.service, 'model': a.model, 'base': a.base, 'backup': str(backup),
                  'admin_overrides_migrated': len(selected), 'runtime_environment_verified': True,
                  'product_acceptance': 'PENDING'}))
