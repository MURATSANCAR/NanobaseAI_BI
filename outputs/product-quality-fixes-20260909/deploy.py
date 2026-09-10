"""Reviewed file deployment with backup and automatic service-health rollback."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import time
import urllib.request

root=Path('/data/nanobaseai/bi/backups/product-quality-20260909')
live=Path('/data/nanobaseai/bi/frontend')
stage=root/'release'
stage.mkdir(exist_ok=True)
with tarfile.open('/tmp/product-quality-release.tgz') as archive:
    for member in archive.getmembers():
        if not (stage/member.name).resolve().is_relative_to(stage.resolve()) or member.issym() or member.islnk():
            raise ValueError('Unexpected archive path')
    archive.extractall(stage, filter='data')
files=[p for p in stage.rglob('*') if p.is_file()]
backup=root/'before-code.tgz'
if backup.exists():
    raise RuntimeError('Backup already exists; use an explicit new release for another deployment')
with tarfile.open(backup,'w:gz') as archive:
    for p in files:
        rel=p.relative_to(stage)
        target=(Path('/data/nanobaseai/bi/cockpit/dist')/p.relative_to(stage/'apps/cockpit/dist')
                if rel.parts[:3]==('apps','cockpit','dist') else live/rel)
        if target.exists():
            archive.add(target,arcname=str(target).lstrip('/'))
manifest=[]
try:
    # Existing hashed assets remain available for already-open clients; HTML is last.
    for p in sorted(files,key=lambda p:p.name=='index.html'):
        rel=p.relative_to(stage)
        target=(Path('/data/nanobaseai/bi/cockpit/dist')/p.relative_to(stage/'apps/cockpit/dist')
                if rel.parts[:3]==('apps','cockpit','dist') else live/rel)
        target.parent.mkdir(parents=True,exist_ok=True)
        temp=target.with_name(target.name+'.release-tmp')
        shutil.copyfile(p,temp)
        os.chmod(temp,0o644)
        os.replace(temp,target)
        manifest.append({'path':str(target),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    subprocess.run(['systemctl','restart','nanobase-semantic-bridge'],check=True)
    health=None
    for attempt in range(30):
        try:
            with urllib.request.urlopen('http://127.0.0.1:8795/health',timeout=3) as response:
                health=json.load(response)
            if health.get('status')=='ok':break
        except Exception:time.sleep(1)
    if not health or health.get('status')!='ok':raise RuntimeError('Service did not become healthy')
    (root/'deployment.json').write_text(json.dumps({'files':manifest,'health':health,'backup':str(backup)},indent=2))
    print(json.dumps({'deployedFiles':len(manifest),'health':health,'backup':str(backup)}),flush=True)
except BaseException:
    with tarfile.open(backup) as archive:archive.extractall('/',filter='data')
    subprocess.run(['systemctl','restart','nanobase-semantic-bridge'],check=False)
    raise
