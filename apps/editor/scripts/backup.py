#!/usr/bin/env python3
"""Consistent offline snapshot: quiesce writers, dump DB and archive original/derived files."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
os.chdir(root)
destination = Path(sys.argv[1]).resolve()
destination.mkdir(mode=0o700, parents=True, exist_ok=False)
compose = ['docker', 'compose']
config = json.loads(subprocess.check_output(compose + ['config', '--format', 'json']))
project = config['name']
image = config['services']['api']['image']
volume = config['volumes']['artifacts']['name']
active_parsers = subprocess.check_output(['docker','ps','-q','--filter','label=com.docker.compose.project='+project,
                                         '--filter','label=com.docker.compose.service=document'],text=True).strip()
if active_parsers:
    raise SystemExit('Finish the active document probe before taking a consistent artifact backup.')
subprocess.run(compose + ['stop', 'api', 'worker'], check=True)
try:
    with (destination / 'database.dump').open('wb') as stream:
        subprocess.run(compose + ['exec', '-T', 'postgres', 'pg_dump', '-U', 'postgres', '-d', 'editor', '-Fc', '--schema=editor', '--schema=checkpoints', '--no-owner', '--no-acl'], stdout=stream, check=True)
    # Tar is streamed from a read-only volume; no book content is logged.
    code = 'import tarfile,sys; t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|"); t.add("/data",arcname="artifacts"); t.close()'
    with (destination / 'artifacts.tar').open('wb') as stream:
        subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL', '-v', volume+':/data:ro', image, 'python', '-c', code], stdout=stream, check=True)
    query = "SELECT json_build_object('revision',(SELECT version_num FROM editor.alembic_version),'deployments',(SELECT json_agg(release ORDER BY release) FROM editor.deployments),'sources',COALESCE((SELECT json_agg(json_build_object('sha256',sha256,'manifest_md5',md5(manifest::text)) ORDER BY sha256) FROM editor.source_probes),'[]'::json))"
    reference = json.loads(subprocess.check_output(compose + ['exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query]))
    manifest = {'project': project, 'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'release': config['services']['api']['environment']['EDITOR_RELEASE'],
                'reference': reference, 'files': {},
                'scope': 'PostgreSQL and artifacts. Qdrant is rebuildable; no qualified book index yet.'}
    for name in ('database.dump', 'artifacts.tar'):
        with (destination/name).open('rb') as stream:
            manifest['files'][name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    (destination/'manifest.json').write_text(json.dumps(manifest, indent=2))
    print('Backup complete: ' + str(destination))
finally:
    subprocess.run(compose + ['start', 'worker', 'api'], check=True)
