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
with_models = '--with-models' in sys.argv
if with_models:
    model_config = json.loads(subprocess.check_output(['docker','compose','-f','compose.yaml','-f','compose.models.yaml','--profile','models','config','--format','json']))
    images = sorted(set(images) | {service['image'] for service in model_config['services'].values()})
    model_manifest = json.loads((root/'deploy/models.json').read_text())
    model_destination = source/'runtime/models'
    model_destination.mkdir(parents=True)
    for item in model_manifest['files']:
        path = root/'runtime/models'/item['name']
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest() != item['sha256']:
                raise SystemExit('Model not verified: '+item['name'])
        shutil.copyfile(path,model_destination/item['name'])
    for name in ('bge-m3-Q8_0.gguf','bge-reranker-v2-m3-Q8_0.gguf'):
        shutil.copyfile(root/'runtime/models'/name,model_destination/name)
inspection = json.loads(subprocess.check_output(['docker','image','inspect',*images]))
subprocess.run(['docker','image','save','-o',str(destination/'images.tar'),*images],check=True)
manifest = {'kind':'editor-foundation-offline', 'architecture':'linux/amd64',
            'release':config['services']['api']['environment']['EDITOR_RELEASE'],
            'images':[{'id':i['Id'],'tags':i['RepoTags'],'digests':i['RepoDigests']} for i in inspection],
            'model_qualification':'candidate weights included; semantic acceptance pending' if with_models else 'pending; LLM/VLM weights not included', 'files':{}}
for path in sorted(destination.rglob('*')):
    if path.is_file():
        with path.open('rb') as stream:
            manifest['files'][str(path.relative_to(destination))] = hashlib.file_digest(stream,'sha256').hexdigest()
(destination/'release-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Offline foundation bundle: '+str(destination))
