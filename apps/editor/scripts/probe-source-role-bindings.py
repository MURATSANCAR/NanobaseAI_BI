#!/usr/bin/env python3
"""Remote source/claim role-binding candidate probe; no expected answers or application writes."""
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
p.add_argument('--support-module',action='append',default=[])
p.add_argument('--reuse-probe')
a=p.parse_args();generation=str(uuid.UUID(a.generation));pages=sorted({int(v) for v in a.pages.split(',')})
assert pages and min(pages)>0 and len(pages)<=10
assert sys.platform.startswith('linux') and os.environ.get('EDITOR_VERIFY_REMOTE_HOST')==socket.gethostname()
root=Path(os.environ['EDITOR_VERIFY_ROOT']);module=Path(a.module).read_text()
support_modules={}
for value in a.support_module:
    path=Path(value);name=path.stem
    assert name.isidentifier() and path.suffix=='.py' and name not in support_modules
    support_modules[name]=path.read_text()
reuse=None
if a.reuse_probe:
    raw=Path(a.reuse_probe).read_bytes();prior=json.loads(raw)
    assert prior['generation_id']==generation and prior['api_pg_match'] is True and prior['protected_before']==prior['protected_after']
    reuse={'artifact_sha256':hashlib.sha256(raw).hexdigest(),'artifact_path':str(Path(a.reuse_probe).resolve()),'artifact_code_sha256':prior['candidate_sha256'],'rows':{r['passage_id']:r for r in prior['results']}}
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
from editor.semantic_acceptance import source_regions
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
for name,source in p['support_modules'].items():
 module=types.ModuleType('editor.'+name);sys.modules[module.__name__]=module
 exec(compile(source,name+'.py','exec'),module.__dict__)
m=types.ModuleType('binding_candidate');exec(compile(p['module'],'role-binding-candidate.py','exec'),m.__dict__)
output=[]
for row in p['records']['source_passages']:
 data=row['data'];spans=[r for r in p['records']['source_spans'] if r['data']['pdf_page']==data['pdf_page']]
 allowed={r['id']:r for r in spans if r['data']['status']=='TEXT_AGREED' and r['data']['role']=='TEXT'}
 regions=source_regions(data['source_span_refs'],allowed)
 if p['reuse']:
  old=p['reuse']['rows'][row['id']];prior=old['review']
  assert old['passage_sha256']==m.digest(data) and prior['claim_sha256']==m.digest(data['claim']['text']) and prior['source_sha256']==m.digest(regions),'REUSE_INPUT_CHANGED'
  review=m.review_from_graphs(data['claim'],regions,prior['source_graph'],prior['claim_graph'],model,artifact_version=prior['version'],artifact_sha256=p['reuse']['artifact_sha256'],artifact_path=p['reuse']['artifact_path'],artifact_code_sha256=p['reuse']['artifact_code_sha256'])
  assert review['source_graph']==prior['source_graph'] and review['claim_graph']==prior['claim_graph'],'REUSED_GRAPH_CHANGED'
 else:
  review=m.review(data['claim'],regions,model)
 output.append({'passage_id':row['id'],'passage_sha256':m.digest(data),'pdf_page':data['pdf_page'],'claim':data['claim'],'review':review})
 if len(output)%10==0:
  print(json.dumps({'progress_completed':len(output),'model_passed':sum(r['review']['passed'] for r in output),'blocked':sum(not r['review']['passed'] for r in output),'semantic_acceptance':False}),file=sys.stderr,flush=True)
after=fingerprint();assert before==after,'PROTECTED_RECORDS_CHANGED'
print(json.dumps({'generation_id':p['generation'],'pages':p['pages'],'candidate_sha256':hashlib.sha256(p['module'].encode()).hexdigest(),'support_module_sha256':{name:hashlib.sha256(source.encode()).hexdigest() for name,source in p['support_modules'].items()},'runtime_code_manifest':code_manifest(),'protected_before':before,'protected_after':after,'api_pg_match':True,'application_writes':0,'semantic_acceptance':False,'results':output},ensure_ascii=False))
'''
payload={'generation':generation,'pages':pages,'module':module,'support_modules':support_modules,'records':records,'reuse':reuse}
raw=subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],cwd=root,input=json.dumps(payload).encode())
report=json.loads(raw)
destination=root/'evidence'/('source-role-bindings-probe-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
report['driver_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
with destination.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
destination.chmod(0o600)
print(json.dumps({'evidence':str(destination),'records':len(report['results']),'passed':sum(r['review']['passed'] for r in report['results']),'application_writes':0,'semantic_acceptance':False}))
