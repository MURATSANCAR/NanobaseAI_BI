#!/usr/bin/env python3
"""Create an offline foundation release, including images and exact file checksums; no secrets/books."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
os.chdir(root)
destination = Path(sys.argv[1]).resolve()
destination.mkdir(parents=True, exist_ok=False)
source = destination/'editor'
shutil.copytree(root, source, ignore=shutil.ignore_patterns('.env','secrets','runtime','dist','evidence','__pycache__'))
config = json.loads(subprocess.check_output(['docker','compose','--profile','tools','config','--format','json']))
images = sorted({service['image'] for service in config['services'].values()})
inspection = json.loads(subprocess.check_output(['docker','image','inspect',*images]))
subprocess.run(['docker','image','save','-o',str(destination/'images.tar'),*images],check=True)
manifest = {'kind':'editor-foundation-offline', 'architecture':'linux/amd64',
            'release':config['services']['api']['environment']['EDITOR_RELEASE'],
            'images':[{'id':i['Id'],'tags':i['RepoTags'],'digests':i['RepoDigests']} for i in inspection],
            'model_qualification':'pending; LLM/VLM weights are not included in this foundation bundle', 'files':{}}
for path in sorted(destination.rglob('*')):
    if path.is_file():
        with path.open('rb') as stream:
            manifest['files'][str(path.relative_to(destination))] = hashlib.file_digest(stream,'sha256').hexdigest()
(destination/'release-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Offline foundation bundle: '+str(destination))
