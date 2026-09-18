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
subprocess.run(['docker','load','-i',str(root/'images.tar')],check=True)
for role,image in manifest['images'].items():
    actual=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',image['tag']],text=True).strip()
    assert actual==image['id'],'GPU_IMAGE_ID_MISMATCH:'+role
subprocess.run(['docker','compose','-f',str(root/'compose.yaml'),'config','--quiet'],cwd=root,check=True)
print(json.dumps({'gpu_package_hashes_match':True,'images':len(manifest['images']),
                  'models':manifest['models'],'containers_started':False,'fresh_gpu_install_verified':False}))
