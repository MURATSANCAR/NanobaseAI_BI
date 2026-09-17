#!/usr/bin/env python3
"""Build a portable offline reader image from verified, pinned local weights."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

root=Path(__file__).resolve().parents[1];os.chdir(root)
source=root/'runtime/ocr-vl';manifest=json.loads((source/'manifest.json').read_text())
stage=root/'runtime/ocr-vl-image';(stage/'model').mkdir(parents=True,exist_ok=True)
for name,entry in manifest['files'].items():
    path=source/name
    with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==entry['sha256']
    target=stage/'model'/name
    if target.exists():target.unlink()
    os.link(path,target)
shutil.copy2(source/'manifest.json',stage/'model/manifest.json')
for name in ('Dockerfile','run.py'):shutil.copy2(root/'ocr-vl'/name,stage/name)
config=json.loads(subprocess.check_output(['docker','compose','--profile','tools','config','--format','json'],text=True))
base=config['services']['document']['image']
subprocess.run(['docker','build','--pull=false','--build-arg','DOCUMENT_IMAGE='+base,
                '-t','nanobase-editor-ocr-vl:1.6-20260917',str(stage)],check=True)
