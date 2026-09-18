#!/usr/bin/env python3
"""Derive a new immutable GPU release after changing a live runner profile.

Large already-exported files are hardlinked; changed metadata is replaced with
new inodes. The old release is preserved. Import must verify every byte again.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('destination')
p.add_argument('--container',default='qwen38-flash-next');args=p.parse_args()
source=Path(args.source).resolve();dest=Path(args.destination).resolve()
assert not dest.exists() and not dest.is_relative_to(source),'INVALID_NEW_RELEASE_PATH'
raw=(source/'gpu-release-manifest.json').read_bytes();manifest=json.loads(raw)
live=json.loads(subprocess.check_output(['docker','inspect',args.container]))[0]
assert live['Image']==manifest['images']['qwen']['id'],'RUNNER_IMAGE_CHANGED_REEXPORT_REQUIRED'
command=live['Config']['Cmd']
assert command[0]==manifest['models']['qwen']['repository'],'MODEL_CHANGED_REEXPORT_REQUIRED'
assert not any(v.split('=',1)[0] in ('--api-key','--hf-token','--token') for v in command),'SECRET_BEARING_COMMAND'
shutil.copytree(source,dest,copy_function=os.link)
def replace(name,data):
    path=dest/name;tmp=path.with_name(path.name+'.new')
    with tmp.open('xb') as stream:stream.write(data)
    os.replace(tmp,path)
compose=json.loads((source/'compose.yaml').read_bytes())
compose['services']['qwen']['command']=command
test=compose['services']['qwen']['healthcheck']['test']
assert test[:2] in (['CMD','python'],['CMD','python3']),'UNEXPECTED_HEALTHCHECK'
test[1]='python3'
data=(json.dumps(compose,indent=2)+'\n').encode();replace('compose.yaml',data)
manifest['files']['compose.yaml']=hashlib.sha256(data).hexdigest()
for model in manifest['models'].values():
    name=str(Path('hf-cache/hub')/('models--'+model['repository'].replace('/','--'))/'refs/main')
    data=model['revision'].encode();replace(name,data)
    manifest['files'][name]=hashlib.sha256(data).hexdigest()
for name in ('import-bundle.py','INSTALL.md'):
    data=Path(__file__).with_name(name).read_bytes();replace(name,data)
    manifest['files'][name]=hashlib.sha256(data).hexdigest()
manifest.update(created_at=time.time(),derived_from_manifest_sha256=hashlib.sha256(raw).hexdigest(),
    qualification='LIVE_RUNNER_PROFILE_UPDATED_REQUIRES_IMPORT_AND_FRESH_GPU_ACCEPTANCE',
    derivation='SAME_WEIGHTS_AND_IMAGES_PINNED_CACHE_REFS_AND_LIVE_QWEN_COMMAND_UPDATED')
replace('gpu-release-manifest.json',json.dumps(manifest,indent=2).encode())
assert (source/'gpu-release-manifest.json').read_bytes()==raw,'PREVIOUS_RELEASE_CHANGED'
subprocess.run(['docker','compose','-f',str(dest/'compose.yaml'),'config','--quiet'],cwd=dest,check=True)
print(json.dumps({'destination':str(dest),'source_unchanged':True,'full_hash_import_required':True}))
