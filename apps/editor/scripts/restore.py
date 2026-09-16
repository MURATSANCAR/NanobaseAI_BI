#!/usr/bin/env python3
"""Restore only into a new, separately named installation. Never overwrite a running source."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from snapshot_reference import book_reference

root = Path(__file__).resolve().parents[1]
os.chdir(root)
if len(sys.argv) != 3:
    raise SystemExit('Usage: python3 scripts/restore.py BACKUP_DIRECTORY EXACT_NEW_COMPOSE_PROJECT_NAME')
source = Path(sys.argv[1]).resolve()
manifest = json.loads((source/'manifest.json').read_text())
compose = ['docker', 'compose']
config = json.loads(subprocess.check_output(compose+['config','--format','json']))
project = config['name']
if project != sys.argv[2] or project == manifest['project']:
    raise SystemExit('Restore requires a separately named target, explicitly specified.')
if subprocess.check_output(compose+['ps','-aq'],text=True).strip():
    raise SystemExit('Target must be new: containers already exist.')
existing = subprocess.check_output(['docker','volume','ls','-q','--filter','label=com.docker.compose.project='+project],text=True).strip()
if existing:
    raise SystemExit('Target volumes already exist; choose a fresh project name.')
subprocess.run([sys.executable,'scripts/preflight.py'],check=True)
for name, expected in manifest['files'].items():
    if name not in ('database.dump','artifacts.tar'):
        raise SystemExit('Unexpected backup member')
    with (source/name).open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest() != expected:
            raise SystemExit('Backup hash mismatch: '+name)
subprocess.run(compose+['up','-d','--no-build','--pull','never','--wait','postgres'],check=True)
with (source/'database.dump').open('rb') as stream:
    subprocess.run(compose+['exec','-T','postgres','pg_restore','-U','postgres','-d','editor','--clean','--if-exists','--no-owner','--no-acl','--role=editor_owner','--exit-on-error'],stdin=stream,check=True)
subprocess.run(compose+['run','--rm','--no-deps','storage-init'],check=True)
volume = config['volumes']['artifacts']['name']
image = config['services']['api']['image']
code = 'import tarfile,sys; t=tarfile.open(fileobj=sys.stdin.buffer,mode="r|"); t.extractall("/data",filter="data")'
# Volume is mounted at the archived top-level name.
with (source/'artifacts.tar').open('rb') as stream:
    subprocess.run(['docker','run','--rm','-i','--network','none','--read-only','--cap-drop','ALL',
                    '--tmpfs','/data:mode=1777','-v',volume+':/data/artifacts',image,'python','-c',code],stdin=stream,check=True)
# Compare the snapshot before starting writers, which can legitimately resume jobs.
book_verified = False
if 'book_reference' in manifest:
    if book_reference(config) != manifest['book_reference']:
        raise SystemExit('Restored book records or artifact bytes differ from backup')
    book_verified = True
query = "SELECT json_build_object('revision',(SELECT version_num FROM editor.alembic_version),'deployments',(SELECT json_agg(release ORDER BY release) FROM editor.deployments),'sources',COALESCE((SELECT json_agg(json_build_object('sha256',sha256,'manifest_md5',md5(manifest::text)) ORDER BY sha256) FROM editor.source_probes),'[]'::json))"
reference = json.loads(subprocess.check_output(compose+['exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query]))
if reference != manifest['reference']:
    raise SystemExit('Restored database differs from backup reference')
subprocess.run(compose+['up','-d','--no-build','--pull','never','--wait','--wait-timeout','600'],check=True)
subprocess.run([sys.executable,'scripts/verify.py'],check=True)
print(json.dumps({'restore':'verified','target':project,'reference':reference,
                  'book_records_and_artifacts_equal':book_verified,
                  'search_rebuild':'REQUIRED: scripts/rebuild-search.py '+project,
                  'book_api_citation_validation':'REQUIRES_REAL_API_VERIFICATION'}))
