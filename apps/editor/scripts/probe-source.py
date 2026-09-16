#!/usr/bin/env python3
"""Bounded remote-server source probe. Stops its container on timeout or interruption."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('source',type=Path)
parser.add_argument('--timeout',type=int,default=1200)
args = parser.parse_args()
if args.timeout < 30 or args.timeout > 7200:
    raise SystemExit('Timeout must be between 30 and 7200 seconds')
source = args.source.resolve(strict=True)
root = Path(__file__).resolve().parents[1]
os.chdir(root)
compose = ['docker','compose','--profile','tools']
config = json.loads(subprocess.check_output(compose+['config','--format','json']))
name = config['name']+'-document-probe'
existing = subprocess.run(['docker','inspect',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if existing.returncode == 0:
    raise SystemExit('An existing source probe owns this installation; do not run a duplicate.')
with source.open('rb') as stream:
    digest = hashlib.file_digest(stream,'sha256').hexdigest()
try:
    subprocess.run(compose+['run','--rm','--no-deps','--name',name,
                           '-e','EDITOR_PARSE_TIMEOUT='+str(args.timeout),
                           '-v',str(source)+':/input/book.pdf:ro',
                           'document','/input/book.pdf','--output','/data/artifacts','--docling'],
                   check=True,timeout=args.timeout+60)
except (subprocess.TimeoutExpired, KeyboardInterrupt):
    subprocess.run(['docker','stop','--time','10',name],check=False)
    raise
subprocess.run(['docker','compose','exec','-T','api','python','-m','editor.record_probe',
                '/data/artifacts/'+digest+'/manifest.json'],check=True)
subprocess.run(['python3','scripts/verify.py'],check=True)
