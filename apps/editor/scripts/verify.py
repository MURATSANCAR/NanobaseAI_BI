#!/usr/bin/env python3
"""Read-only checks against the deployed API and independent actual PostgreSQL query."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.error

root = Path(__file__).resolve().parents[1]
os.chdir(root)
settings = dict(line.split('=',1) for line in (root/'.env').read_text().splitlines() if line and not line.startswith('#'))
base = 'http://127.0.0.1:' + settings['EDITOR_PORT']
token = (root/'secrets/api_token').read_text().strip()
with urllib.request.urlopen(urllib.request.Request(base+'/v1/system', headers={'Authorization':'Bearer '+token}), timeout=20) as response:
    state = json.load(response)
query = "SELECT json_build_object('revision',(SELECT version_num FROM editor.alembic_version),'deployments',(SELECT json_agg(release ORDER BY release) FROM editor.deployments),'app_superuser',(SELECT rolsuper FROM pg_roles WHERE rolname='editor_app'))"
reference = json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query], text=True))
assert state['infrastructure_ready'], state['checks']
assert state['details']['schema_revision'] == reference['revision']
assert [row['release'] for row in state['details']['deployments']] == reference['deployments']
assert reference['app_superuser'] is False
try:
    urllib.request.urlopen(base+'/v1/system', timeout=10)
    raise AssertionError('Unauthenticated request allowed')
except urllib.error.HTTPError as exc:
    assert exc.code == 401
print(json.dumps({'environment':'remote Linux Docker installation', 'api':base,
                  'database':'isolated editor PostgreSQL / editor schema',
                  'state':state, 'independent_reference':reference, 'unauthorized_status':401}, indent=2))
