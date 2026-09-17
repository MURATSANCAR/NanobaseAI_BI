#!/usr/bin/env python3
"""Compare deployed application bytes with this checkout; does not execute tests locally."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
os.chdir(root)
expected = {str(path.relative_to(root/'backend')):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (root/'backend').rglob('*') if path.is_file() and '__pycache__' not in path.parts}
code = '''import hashlib,json,pathlib
r=pathlib.Path('/app')
print(json.dumps({str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob('*') if p.is_file() and '__pycache__' not in p.parts}))'''
actual = json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code]))
assert expected == actual, 'Deployed application differs from release checkout'
identity = hashlib.sha256(json.dumps(expected,sort_keys=True).encode()).hexdigest()
print(json.dumps({'application_bytes_match':True,'backend_tree_sha256':identity,'files':len(expected)},indent=2))

if os.environ.get('EDITOR_VERIFY_WEB')=='1':
    frontend=root/'frontend'
    paths=list((frontend/'src').rglob('*'))+[frontend/n for n in ('package.json','package-lock.json','index.html','tsconfig.json','vite.config.ts')]
    expected_web={str(p.relative_to(frontend)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
    manifest=json.loads(subprocess.check_output(['docker','compose','exec','-T','gateway','cat','/usr/share/nginx/html/editor/build-manifest.json']))
    assert manifest['sources']==expected_web,'Web image was not built from this source checkout'
    for name,wanted in manifest['outputs'].items():
        actual_file=subprocess.check_output(['docker','compose','exec','-T','gateway','cat','/usr/share/nginx/html/editor/'+name])
        assert hashlib.sha256(actual_file).hexdigest()==wanted,'Web output changed: '+name
    print(json.dumps({'web_source_and_output_hashes_match':True,'web_source_files':len(expected_web)}))
