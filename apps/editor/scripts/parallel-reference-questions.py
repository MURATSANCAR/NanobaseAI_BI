#!/usr/bin/env python3
"""Temporarily use four workers for this real run's 13 acceptance questions only."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import urllib.error
import http.client

root=Path(__file__).resolve().parents[1]; os.chdir(root)
run=json.loads((root/'evidence/reference-book-run.json').read_text())
job=run['job']['job_id']; gen=run['job']['generation_id']
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
deadline=time.monotonic()+86400
scaled=False
def analysis_state():
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8810/v1/jobs/'+job,headers=headers),timeout=30) as response:
                state=json.load(response)
                if attempt: print(json.dumps({'api_recovered_after_retries':attempt}),flush=True)
                return state
        except urllib.error.HTTPError as exc:
            if exc.code not in (502,503,504) or attempt==4: raise
            print(json.dumps({'api_retry':attempt+1,'http_status':exc.code}),flush=True)
        except (urllib.error.URLError, ConnectionError, TimeoutError,
                http.client.RemoteDisconnected, http.client.IncompleteRead):
            if attempt==4: raise
            print(json.dumps({'api_retry':attempt+1,'error':'URLError'}),flush=True)
        time.sleep(min(30,2**(attempt+1)))
try:
    while time.monotonic()<deadline:
        state=analysis_state()
        if state['status'] in ('FAILED','CANCELLED'): raise RuntimeError('ANALYSIS_NOT_COMPLETED')
        if state['status']=='COMPLETED': break
        time.sleep(30)
    else: raise TimeoutError('ANALYSIS_WAIT_LIMIT')
    subprocess.run(['docker','compose','up','-d','--no-deps','--scale','worker=4','worker'],check=True)
    scaled=True
    print(json.dumps({'generation_id':gen,'question_workers':4}),flush=True)
    while time.monotonic()<deadline:
        query="SELECT json_build_object('total',count(*),'terminal',count(*) FILTER(WHERE status IN ('COMPLETED','FAILED','CANCELLED'))) FROM editor.jobs WHERE task='question' AND generation_id='"+gen+"'"
        counts=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))
        if counts['total']>=13 and counts['terminal']==counts['total']:
            print(json.dumps(counts),flush=True); break
        time.sleep(30)
    else: raise TimeoutError('QUESTION_WAIT_LIMIT')
finally:
    if scaled:
        subprocess.run(['docker','compose','up','-d','--no-deps','--scale','worker=1','worker'],check=True)
        print('Restored one worker',flush=True)
