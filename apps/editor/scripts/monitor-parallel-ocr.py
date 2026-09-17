#!/usr/bin/env python3
"""Read-only live acceptance monitor; one instance per real analysis job."""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1];job=str(uuid.UUID(sys.argv[1]))
lock=(root/'evidence'/f'parallel-monitor-{job}.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
base='http://127.0.0.1:8810'
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=30) as response:return json.load(response)
state={'job_id':job,'verified_pages':[],'failed_pages':[],'status':'RUNNING'}
path=root/'evidence'/f'parallel-monitor-{job}.json'
for attempt in range(4320):
    try:
        status=get('/v1/jobs/'+job);gen=status['generation_id']
        pages=get(f'/v1/generations/{gen}/page_checks?limit=100')['items']
        for page in pages:
            n=page['data']['pdf_page']
            if n in state['verified_pages'] or n in state['failed_pages']:continue
            result=subprocess.run([sys.executable,str(root/'scripts/verify-parallel-ocr.py'),gen,str(n)],capture_output=True,text=True)
            (state['verified_pages'] if result.returncode==0 else state['failed_pages']).append(n)
            (root/'evidence'/f'parallel-monitor-{job}-page-{n:04}.log').write_text(result.stdout+result.stderr)
        state.update({'generation_id':gen,'job_status':status['status'],'progress':status['progress'],'checked_at':time.time()})
        if status['status'] in ('COMPLETED','FAILED','CANCELLED'):
            state['status']='TECHNICAL_PASS' if status['status']=='COMPLETED' and not state['failed_pages'] and len(state['verified_pages'])==status['source_coverage']['expected_pages'] else 'INCOMPLETE_OR_FAILED'
        state['semantic_acceptance']=False
        temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2));temporary.replace(path)
        if state['status']!='RUNNING':break
    except Exception as error:
        print(type(error).__name__,flush=True)
    time.sleep(10)
