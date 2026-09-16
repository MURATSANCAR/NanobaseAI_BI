#!/usr/bin/env python3
"""Online packaging step only. Download pinned public assets; verify bytes before promotion."""
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root/'deploy/models.json').read_text())
destination = root/'runtime/models'
destination.mkdir(parents=True,exist_ok=True)
for item in manifest['files']:
    path = destination/item['name']
    if path.exists():
        with path.open('rb') as stream:
            if path.stat().st_size == item['bytes'] and hashlib.file_digest(stream,'sha256').hexdigest() == item['sha256']:
                print('Already verified: '+item['name'],flush=True)
                continue
        raise SystemExit('Existing model mismatch: '+str(path))
    temporary = path.with_suffix('.partial')
    url = 'https://huggingface.co/'+manifest['repository']+'/resolve/'+manifest['revision']+'/'+item['name']
    subprocess.run(['curl','--fail','--location','--retry','3','--connect-timeout','20','--max-time','7200','--continue-at','-',
                    '--output',str(temporary),url],check=True)
    with temporary.open('rb') as stream:
        if temporary.stat().st_size != item['bytes'] or hashlib.file_digest(stream,'sha256').hexdigest() != item['sha256']:
            raise SystemExit('Downloaded model hash mismatch: '+item['name'])
    temporary.rename(path)
    print('Verified: '+item['name'],flush=True)
