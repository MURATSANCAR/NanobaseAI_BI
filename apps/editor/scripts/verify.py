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
query = "SELECT json_build_object('revision',(SELECT version_num FROM editor.alembic_version),'deployments',(SELECT json_agg(release ORDER BY release) FROM editor.deployments),'source_probes',COALESCE((SELECT json_agg(json_build_object('sha256',sha256,'bytes',(manifest->>'bytes')::bigint,'pages',(manifest->>'pdf_pages')::integer) ORDER BY sha256) FROM editor.source_probes),'[]'::json),'app_superuser',(SELECT rolsuper FROM pg_roles WHERE rolname='editor_app'))"
reference = json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query], text=True))
assert state['infrastructure_ready'], state['checks']
assert state['details']['schema_revision'] == reference['revision']
assert [row['release'] for row in state['details']['deployments']] == reference['deployments']
assert reference['app_superuser'] is False
assert state['details']['source_probes'] == reference['source_probes']
if 'models' in settings.get('COMPOSE_PROFILES','').split(','):
    with urllib.request.urlopen(urllib.request.Request(base+'/v1/model-services',headers={'Authorization':'Bearer '+token}),timeout=20) as response:
        models = json.load(response)
    assert all(item['ready'] for item in models['services'].values()), models
for source in reference['source_probes']:
    with urllib.request.urlopen(urllib.request.Request(base+'/v1/source-probes/'+source['sha256'], headers={'Authorization':'Bearer '+token}),timeout=20) as response:
        manifest = json.load(response)
    assert manifest['pdf_pages'] == source['pages'] == len(manifest['pages'])
    assert manifest['bytes'] == source['bytes']
    expected_manifest = json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',
        "SELECT manifest FROM editor.source_probes WHERE sha256='"+source['sha256']+"'"],text=True))
    assert manifest == expected_manifest, 'Full API manifest differs from the independent DB reference'
    code = '''import hashlib,json,pathlib,sys
p=pathlib.Path('/data/artifacts')/sys.argv[1]
m=json.loads((p/'manifest.json').read_text())
with (p/'original.pdf').open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==m['sha256']
for page in m['pages']:
 with (p/('page-%04d.png'%page['pdf_page'])).open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==page['render_sha256']
print('Original source and every render hash verified')'''
    subprocess.run(['docker','compose','exec','-T','api','python','-c',code,source['sha256']],check=True)
try:
    urllib.request.urlopen(base+'/v1/system', timeout=10)
    raise AssertionError('Unauthenticated request allowed')
except urllib.error.HTTPError as exc:
    assert exc.code == 401
print(json.dumps({'environment':'remote Linux Docker installation', 'api':base,
                  'database':'isolated editor PostgreSQL / editor schema',
                  'state':state, 'independent_reference':reference, 'unauthorized_status':401}, indent=2))
