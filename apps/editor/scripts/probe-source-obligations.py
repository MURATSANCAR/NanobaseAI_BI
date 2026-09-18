#!/usr/bin/env python3
"""Remote immutable saved-passage probe; no expected answers or application writes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

p=argparse.ArgumentParser()
p.add_argument('generation');p.add_argument('module');p.add_argument('--pages',required=True)
a=p.parse_args();generation=str(uuid.UUID(a.generation));pages=sorted({int(v) for v in a.pages.split(',')})
assert pages and min(pages)>0 and len(pages)<=10
assert sys.platform.startswith('linux') and os.environ.get('EDITOR_VERIFY_REMOTE_HOST')==socket.gethostname()
root=Path(os.environ['EDITOR_VERIFY_ROOT']);module=Path(a.module).read_text()
token=(root/'secrets/api_token').read_text().strip()
records={}
for kind in ('source_spans','source_passages'):
    rows=[]
    for page in pages:
        offset=0
        while True:
            request=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}/{kind}?pdf_page={page}&limit=100&offset={offset}',headers={'Authorization':'Bearer '+token})
            with urllib.request.urlopen(request,timeout=180) as response:batch=json.load(response)
            rows.extend(batch['items']);offset+=len(batch['items'])
            if not batch['has_more']:break
            assert batch['items']
    records[kind]=rows
assert 0<len(records['source_passages'])<=32,'BOUNDED_PASSAGE_LIMIT'
code=r'''
import json,sys,types,hashlib
from editor.config import connection,code_manifest
from editor.analysis import model
p=json.load(sys.stdin)
def fingerprint():
 with connection() as db:
  db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
  return {kind:db.execute("SELECT md5(string_agg(md5(row_to_json(r)::text),'' ORDER BY id)) AS hash FROM editor."+kind+" r WHERE generation_id=%s",(p['generation'],)).fetchone()['hash'] for kind in ('records','reviews')}
before=fingerprint()
with connection() as db:
 db.execute('SET TRANSACTION READ ONLY')
 assert db.execute("SELECT count(*) AS n FROM editor.jobs WHERE status IN ('RUNNING','QUEUED')").fetchone()['n']==0,'ACTIVE_MODEL_JOB'
 for kind,api_rows in p['records'].items():
  rows=db.execute("SELECT id,record_key,data FROM editor.records WHERE generation_id=%s AND kind=%s AND (data->>'pdf_page')::int=ANY(%s)",(p['generation'],kind,p['pages'])).fetchall()
  actual={str(r['id']):{'id':str(r['id']),'record_key':r['record_key'],'data':r['data']} for r in rows}
  assert actual=={r['id']:r for r in api_rows},'API_PG_MISMATCH'
m=types.ModuleType('semantic_candidate');exec(compile(p['module'],'semantic-candidate.py','exec'),m.__dict__)
output=[]
for row in p['records']['source_passages']:
 data=row['data'];spans=[r for r in p['records']['source_spans'] if r['data']['pdf_page']==data['pdf_page']]
 allowed={r['id']:r for r in spans if r['data']['status']=='TEXT_AGREED' and r['data']['role']=='TEXT'}
 regions=[{'span_id':ref,**{k:allowed[ref]['data'][k] for k in ('text','bbox','render_sha256')}} for ref in data['source_span_refs']]
 review=m.review(data['claim'],regions,model)
 output.append({'passage_id':row['id'],'passage_sha256':m.digest(data),'pdf_page':data['pdf_page'],'claim':data['claim'],'review':review})
 if len(output)%10==0:
  print(json.dumps({'progress_completed':len(output),'model_passed':sum(r['review']['passed'] for r in output),'blocked':sum(not r['review']['passed'] for r in output),'semantic_acceptance':False}),file=sys.stderr,flush=True)
after=fingerprint();assert before==after,'PROTECTED_RECORDS_CHANGED'
print(json.dumps({'generation_id':p['generation'],'pages':p['pages'],'candidate_sha256':hashlib.sha256(p['module'].encode()).hexdigest(),'runtime_code_manifest':code_manifest(),'protected_before':before,'protected_after':after,'api_pg_match':True,'application_writes':0,'semantic_acceptance':False,'results':output},ensure_ascii=False))
'''
payload={'generation':generation,'pages':pages,'module':module,'records':records}
raw=subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],cwd=root,input=json.dumps(payload).encode())
report=json.loads(raw)
destination=root/'evidence'/('source-obligations-probe-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
report['driver_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
with destination.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
destination.chmod(0o600)
print(json.dumps({'evidence':str(destination),'records':len(report['results']),'passed':sum(r['review']['passed'] for r in report['results']),'application_writes':0,'semantic_acceptance':False}))
