#!/usr/bin/env python3
"""Read-only lexical qualification replay of an actual API/PG/model proof."""
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

p=argparse.ArgumentParser();p.add_argument('prior_proof',type=Path);p.add_argument('module',type=Path)
a=p.parse_args()
assert sys.platform.startswith('linux') and socket.gethostname()==os.environ['EDITOR_VERIFY_REMOTE_HOST']
root=Path(os.environ['EDITOR_VERIFY_ROOT']); prior_bytes=a.prior_proof.read_bytes();prior=json.loads(prior_bytes)
generation=str(uuid.UUID(prior['generation_id']));module=a.module.read_text()
assert prior['api_pg_match'] is True and prior['application_writes']==0
assert prior['protected_before']==prior['protected_after'] and 0<len(prior['results'])<=32
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()};records={}
for kind in ('source_spans','source_passages'):
    rows=[]
    for page in prior['pages']:
        offset=0
        while True:
            req=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}/{kind}?pdf_page={page}&limit=100&offset={offset}',headers=headers)
            with urllib.request.urlopen(req,timeout=120) as response:batch=json.load(response)
            rows.extend(batch['items']);offset+=len(batch['items'])
            if not batch['has_more']:break
            assert batch['items'],'EMPTY_API_PAGINATION'
    records[kind]=rows
code=r'''
import json,sys,types,hashlib
from editor.config import connection,code_manifest
from editor.source_unit_claims import reading_segments
p=json.load(sys.stdin);prior=p['prior'];generation=prior['generation_id']
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def protected():
 with connection() as db:
  db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
  return {kind:db.execute("SELECT md5(string_agg(md5(row_to_json(r)::text),'' ORDER BY id)) AS hash FROM editor."+kind+" r WHERE generation_id=%s",(generation,)).fetchone()['hash'] for kind in ('records','reviews')}
before=protected();assert before==prior['protected_after'],'PRIOR_SOURCE_SNAPSHOT_CHANGED'
assert code_manifest()['source_unit_claims.py']==prior['runtime_code_manifest']['source_unit_claims.py']
with connection() as db:
 db.execute('SET TRANSACTION READ ONLY')
 for kind,api in p['records'].items():
  rows=db.execute("SELECT id,record_key,data FROM editor.records WHERE generation_id=%s AND kind=%s AND (data->>'pdf_page')::int=ANY(%s)",(generation,kind,prior['pages'])).fetchall()
  assert {str(r['id']):{'id':str(r['id']),'record_key':r['record_key'],'data':r['data']} for r in rows}=={r['id']:r for r in api},'API_PG_MISMATCH'
actual={r['id']:r for r in p['records']['source_passages']}
assert set(actual)=={r['passage_id'] for r in prior['results']},'PRIOR_PASSAGE_SET_CHANGED'
m=types.ModuleType('qualification_candidate');exec(compile(p['module'],'qualification-candidate.py','exec'),m.__dict__)
results=[]
for old in prior['results']:
 data=actual[old['passage_id']]['data'];assert digest(data)==old['passage_sha256'] and data['claim']==old['claim']
 spans=[r for r in p['records']['source_spans'] if r['data']['pdf_page']==data['pdf_page']]
 refs=data['source_span_refs'];reading=reading_segments(spans,refs)
 assert reading==old['review']['source_reading_segments'],'SOURCE_READING_PROOF_CHANGED'
 by_id={r['id']:r['data'] for r in spans}
 for region in old['review']['source_regions']:
  source=by_id[region['span_id']]
  assert source['status']=='TEXT_AGREED' and source['role']=='TEXT'
  assert all(region[k]==source[k] for k in ('text','bbox','render_sha256'))
 gate=m.qualification_gate(data['claim']['text'],reading)
 results.append({'passage_id':old['passage_id'],'passage_sha256':old['passage_sha256'],'pdf_page':data['pdf_page'],
  'prior_model_passed':old['review']['passed'],'qualification_gate':gate,'reading_sha256':digest(reading),
  'source_reading_segments':reading,'claim_text':data['claim']['text']})
after=protected();assert before==after,'PROTECTED_SOURCE_CHANGED'
print(json.dumps({'status':'PASS','scope':'READONLY_LEXICAL_COMPONENT_NOT_SEMANTIC_ACCEPTANCE','generation_id':generation,
 'api_pg_match':True,'prior_proof_reading_match':True,'protected_before':before,'protected_after':after,
 'module_sha256':hashlib.sha256(p['module'].encode()).hexdigest(),'module_version':m.VERSION,
 'model_calls':0,'application_writes':0,'semantic_acceptance':False,'results':results},ensure_ascii=False))
'''
payload={'prior':prior,'module':module,'records':records}
output=subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],cwd=root,input=json.dumps(payload).encode())
report=json.loads(output);assert a.module.read_text()==module,'MODULE_CHANGED_DURING_PROBE'
report.update(prior_proof=str(a.prior_proof),prior_proof_sha256=hashlib.sha256(prior_bytes).hexdigest(),driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
out=root/'evidence'/('source-qualification-probe-'+str(uuid.uuid4())+'.json')
with out.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
out.chmod(0o600)
print(json.dumps({'status':report['status'],'records':len(report['results']),'lexically_blocked':sum(not r['qualification_gate']['passed'] for r in report['results']),'prior_model_pass_now_blocked':sum(r['prior_model_passed'] and not r['qualification_gate']['passed'] for r in report['results']),'model_calls':0,'evidence':str(out)}))
