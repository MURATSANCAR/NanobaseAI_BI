#!/usr/bin/env python3
"""Read-only live acceptance monitor; resume checkpoints and preserve attempt logs."""
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
MAX_PAGE_ATTEMPTS=3

def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=30) as response:return json.load(response)

def transient_failure(code, text):
    if 'AssertionError' in text:
        return False
    if code == 75 and 'TRANSIENT_TRANSPORT_EXHAUSTED:' in text:
        return True
    # Migrate only recognisable legacy transport failures, never assertion/schema errors.
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    last=lines[-1] if lines else ''
    return (last.startswith('urllib.error.URLError:')
            and any(reason in last.lower() for reason in
                    ('connection refused', 'connection reset', 'timed out', 'temporary failure in name resolution')))

path=root/'evidence'/f'parallel-monitor-{job}.json'
state=json.loads(path.read_text()) if path.exists() else {'job_id':job,'verified_pages':[],'failed_pages':[],'status':'RUNNING'}
if state.get('job_id') != job:
    raise RuntimeError('MONITOR_CHECKPOINT_JOB_MISMATCH')
state.setdefault('page_attempts', {})
state.setdefault('pending_retry_pages', [])
state.setdefault('retry_history', [])

def persist():
    state['semantic_acceptance']=False
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(state,indent=2));temporary.replace(path)

# Old versions permanently failed a page when nginx briefly restarted. Preserve
# their logs and record the migration; only transport failures are retryable.
for n in list(state['failed_pages']):
    legacy=root/'evidence'/f'parallel-monitor-{job}-page-{n:04}.log'
    count=state['page_attempts'].get(str(n),1)
    previously_classified = any(entry.get('pdf_page') == n for entry in state['retry_history'])
    if not previously_classified and legacy.exists() and count < MAX_PAGE_ATTEMPTS and transient_failure(1,legacy.read_text()):
        state['failed_pages'].remove(n)
        state['page_attempts'][str(n)]=count
        if n not in state['pending_retry_pages']:state['pending_retry_pages'].append(n)
        state['retry_history'].append({'pdf_page':n,'reason':'LEGACY_TRANSIENT_TRANSPORT_RETRY','log':str(legacy),'at':time.time()})
        state['status']='RUNNING'
persist()

for attempt in range(4320):
    try:
        status=get('/v1/jobs/'+job);gen=status['generation_id']
        if state.get('generation_id',gen) != gen:
            raise RuntimeError('MONITOR_CHECKPOINT_GENERATION_MISMATCH')
        pages=get(f'/v1/generations/{gen}/page_checks?limit=100')['items']
        for page in pages:
            n=page['data']['pdf_page']
            if n in state['verified_pages'] or n in state['failed_pages']:continue
            count=state['page_attempts'].get(str(n),0)
            if count >= MAX_PAGE_ATTEMPTS:
                state['failed_pages'].append(n)
                if n in state['pending_retry_pages']:state['pending_retry_pages'].remove(n)
                persist();continue
            number=count+1
            log=root/'evidence'/f'parallel-monitor-{job}-page-{n:04}-attempt-{number:02}.log'
            # A prior interruption may have reserved an attempt; never overwrite it.
            while log.exists():
                number+=1
                log=root/'evidence'/f'parallel-monitor-{job}-page-{n:04}-attempt-{number:02}.log'
            with log.open('x') as output:
                state['page_attempts'][str(n)]=count+1
                persist()
                result=subprocess.run([sys.executable,str(root/'scripts/verify-parallel-ocr.py'),gen,str(n)],stdout=output,stderr=subprocess.STDOUT,text=True)
            text=log.read_text()
            retry=transient_failure(result.returncode,text) and count+1 < MAX_PAGE_ATTEMPTS
            state['retry_history'].append({'pdf_page':n,'attempt':count+1,'returncode':result.returncode,'log':str(log),'retryable':retry,'at':time.time()})
            if result.returncode==0:
                state['verified_pages'].append(n)
            elif not retry:
                state['failed_pages'].append(n)
            if retry:
                if n not in state['pending_retry_pages']:state['pending_retry_pages'].append(n)
            elif n in state['pending_retry_pages']:
                state['pending_retry_pages'].remove(n)
            persist()
        state.update({'generation_id':gen,'job_status':status['status'],'progress':status['progress'],'checked_at':time.time()})
        if status['status'] in ('COMPLETED','FAILED','CANCELLED') and not state['pending_retry_pages']:
            state['status']='TECHNICAL_PASS' if status['status']=='COMPLETED' and not state['failed_pages'] and len(state['verified_pages'])==status['source_coverage']['expected_pages'] else 'INCOMPLETE_OR_FAILED'
        else:
            state['status']='RUNNING'
        persist()
        if state['status']!='RUNNING':break
    except Exception as error:
        print(type(error).__name__,flush=True)
    time.sleep(10)
