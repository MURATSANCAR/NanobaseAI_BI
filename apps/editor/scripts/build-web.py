#!/usr/bin/env python3
"""Build from locked sources; embed source/output hashes to detect stale web images."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
frontend=root/'frontend'
def sources():
    paths=list((frontend/'src').rglob('*'))+[frontend/n for n in ('package.json','package-lock.json','index.html','tsconfig.json','vite.config.ts')]
    return {str(p.relative_to(frontend)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
before=sources()
subprocess.run(['npm','ci','--ignore-scripts'],cwd=frontend,check=True)
subprocess.run(['npm','run','build'],cwd=frontend,check=True)
if sources()!=before:raise RuntimeError('WEB_SOURCES_CHANGED_DURING_BUILD')
outputs={str(p.relative_to(frontend/'dist')):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted((frontend/'dist').rglob('*')) if p.is_file()}
(frontend/'dist/build-manifest.json').write_text(json.dumps({'sources':before,'outputs':outputs},sort_keys=True))
if len(sys.argv)!=2:raise SystemExit('Pass the exact release image tag')
subprocess.run(['docker','build','-t',sys.argv[1],'.'],cwd=frontend,check=True)
