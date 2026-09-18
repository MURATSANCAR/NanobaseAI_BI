#!/usr/bin/env python3
"""Build from locked sources; embed source/output hashes to detect stale web images."""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('image',help='Exact release image tag')
parser.add_argument('--frontend',type=Path,default=root/'frontend',help='Isolated source staging directory')
parser.add_argument('--offline',action='store_true',help='Require the existing npm cache')
args=parser.parse_args();frontend=args.frontend.resolve()
def sources():
    paths=list((frontend/'src').rglob('*'))+[frontend/n for n in ('package.json','package-lock.json','index.html','tsconfig.json','vite.config.ts')]
    return {str(p.relative_to(frontend)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
before=sources()
subprocess.run(['npm','ci','--ignore-scripts']+(['--offline'] if args.offline else []),cwd=frontend,check=True)
subprocess.run(['npm','run','build'],cwd=frontend,check=True)
if sources()!=before:raise RuntimeError('WEB_SOURCES_CHANGED_DURING_BUILD')
outputs={str(p.relative_to(frontend/'dist')):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted((frontend/'dist').rglob('*')) if p.is_file()}
(frontend/'dist/build-manifest.json').write_text(json.dumps({'sources':before,'outputs':outputs},sort_keys=True))
subprocess.run(['docker','build','--network','none','-t',args.image,'.'],cwd=frontend,check=True)
