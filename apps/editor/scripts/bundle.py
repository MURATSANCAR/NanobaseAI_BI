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
config = json.loads(subprocess.check_output(['docker','compose','-f','compose.yaml','--profile','tools','config','--format','json']))
images = sorted({service['image'] for service in config['services'].values()})
with_models = '--with-models' in sys.argv
with_ocr = 'ocr' in config['services'] or '--with-ocr' in sys.argv
if with_ocr:
    ocr_config = json.loads(subprocess.check_output(['docker','compose','-f','compose.yaml','-f','compose.ocr.yaml','config','--format','json']))
    config['services']['ocr'] = ocr_config['services']['ocr']
    images = sorted(set(images) | {ocr_config['services']['ocr']['image']})
if with_models:
    model_config = json.loads(subprocess.check_output(['docker','compose','-f','compose.yaml','-f','compose.models.yaml','--profile','models','config','--format','json']))
    config['services'].update(model_config['services'])
    images = sorted(set(images) | {service['image'] for service in model_config['services'].values()})
    model_manifest = json.loads((root/'deploy/models.json').read_text())
    model_destination = source/'runtime/models'
    model_destination.mkdir(parents=True)
    for item in model_manifest['files'] + model_manifest['reused_files']:
        path = root/'runtime/models'/item['name']
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest() != item['sha256']:
                raise SystemExit('Model not verified: '+item['name'])
        shutil.copyfile(path,model_destination/item['name'])
inspection = json.loads(subprocess.check_output(['docker','image','inspect',*images]))
# docker load need not preserve registry digests. Use content-derived local tags,
# verify image IDs after import, and override every service to those offline tags.
by_reference = dict(zip(images,inspection))
offline_services = {}
tags = set()
for service, definition in config['services'].items():
    identity = by_reference[definition['image']]['Id']
    tag = 'nanobase-editor-release/image:' + identity.split(':')[1][:24]
    subprocess.run(['docker','image','tag',identity,tag],check=True)
    tags.add(tag)
    offline_services[service] = {'image':tag,'pull_policy':'never'}
(source/'compose.offline.yaml').write_text(json.dumps({'services':offline_services},indent=2))
with (source/'.env.example').open('a') as stream:
    stream.write('\nCOMPOSE_FILE=compose.yaml:' + ('compose.models.yaml:' if with_models else '') + ('compose.ocr.yaml:' if with_ocr else '') + 'compose.offline.yaml\n')
    if with_models:
        stream.write('COMPOSE_PROFILES=models\n')
inspection = json.loads(subprocess.check_output(['docker','image','inspect',*sorted(tags)]))
subprocess.run(['docker','image','save','-o',str(destination/'images.tar'),*sorted(tags)],check=True)
manifest = {'kind':'editor-foundation-offline', 'architecture':'linux/amd64',
            'ocr_included':with_ocr,
            'release':config['services']['api']['environment']['EDITOR_RELEASE'],
            'images':[{'id':i['Id'],'tags':[tag],'digests':i['RepoDigests']} for tag,i in zip(sorted(tags),inspection)],
            'model_qualification':'candidate weights included; semantic acceptance pending' if with_models else 'pending; LLM/VLM weights not included', 'files':{}}
for path in sorted(destination.rglob('*')):
    if path.is_file():
        with path.open('rb') as stream:
            manifest['files'][str(path.relative_to(destination))] = hashlib.file_digest(stream,'sha256').hexdigest()
(destination/'release-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Offline foundation bundle: '+str(destination))
