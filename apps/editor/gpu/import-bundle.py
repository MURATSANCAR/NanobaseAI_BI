#!/usr/bin/env python3
"""Verify every packaged byte before importing exact offline GPU images."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root=Path(sys.argv[1]).resolve()
manifest=json.loads((root/'gpu-release-manifest.json').read_text())
assert manifest['kind']=='editor-gpu-offline'
for name,wanted in manifest['files'].items():
    path=(root/name).resolve();assert path.is_relative_to(root),'PACKAGE_PATH_ESCAPE'
    with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
    assert actual==wanted,'PACKAGE_HASH_MISMATCH:'+name
present=[]
for image in manifest['images'].values():
    inspected=subprocess.run(['docker','image','inspect','--format','{{.Id}}',image['tag']],capture_output=True,text=True)
    present.append(inspected.returncode==0 and inspected.stdout.strip()==image['id'])
images_loaded=not all(present)
if images_loaded:subprocess.run(['docker','load','-i',str(root/'images.tar')],check=True)
for role,image in manifest['images'].items():
    actual=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',image['tag']],text=True).strip()
    assert actual==image['id'],'GPU_IMAGE_ID_MISMATCH:'+role
resolutions=[]
for role,model in manifest['models'].items():
    repo=root/'hf-cache/hub'/('models--'+model['repository'].replace('/','--'))
    assert (repo/'refs/main').read_text()==model['revision'],'HF_CACHE_REF_NOT_EXACT:'+role
    assert (repo/'snapshots'/model['revision']/'config.json').is_file(),'HF_SNAPSHOT_CONFIG_MISSING:'+role
    code="import json,pathlib,sys;from huggingface_hub import snapshot_download;p=pathlib.Path(snapshot_download(sys.argv[1],local_files_only=True));assert p.name==sys.argv[2];assert (p/'config.json').is_file();print(json.dumps({'repository':sys.argv[1],'revision':p.name,'offline_snapshot_resolved':True}))"
    raw=subprocess.check_output(['docker','run','--rm','--network','none','--entrypoint','python3',
        '-e','HF_HUB_OFFLINE=1','-v',str(root/'hf-cache')+':/root/.cache/huggingface:ro',
        manifest['images'][role]['tag'],'-c',code,model['repository'],model['revision']],text=True)
    resolutions.append(json.loads(raw))
subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'config','--quiet'],cwd=root,check=True)
print(json.dumps({'gpu_package_hashes_match':True,'images':len(manifest['images']),
                  'images_loaded':images_loaded,
                  'models':manifest['models'],'offline_cache_resolution':resolutions,
                  'model_servers_started':False,'fresh_gpu_install_verified':False}))
