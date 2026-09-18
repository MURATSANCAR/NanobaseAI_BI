#!/usr/bin/env python3
"""Replay an actual saved model candidate through a new semantic gate remotely.

No expected answer, synthetic source, record mutation, or promotion is supplied.
This is component acceptance; a new production generation is still required.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

assert sys.platform.startswith('linux') and os.environ.get('EDITOR_VERIFY_REMOTE_HOST')==socket.gethostname()
p=argparse.ArgumentParser();p.add_argument('evidence');p.add_argument('semantic_module');args=p.parse_args()
root=Path(os.environ['EDITOR_VERIFY_ROOT']).resolve()
prior=json.loads(Path(args.evidence).read_text());module=Path(args.semantic_module).read_text()
payload={'prior':prior,'module':module}
identity=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
out=root/'evidence'/('semantic-candidate-'+identity[:20]+'.json')
assert not out.exists(),'EVIDENCE_ALREADY_EXISTS'
code='''import hashlib,json,sys,types
from editor.config import connection
from editor.analysis import model
p=json.load(sys.stdin);prior=p['prior'];generation=prior['generation_id'];page=prior['pdf_page']
def protected():
 with connection() as db:
  a=db.execute("SELECT md5(string_agg(md5(row_to_json(r)::text),'' ORDER BY id)) AS value FROM editor.records r WHERE generation_id=%s",(generation,)).fetchone()['value']
  b=db.execute("SELECT md5(string_agg(md5(row_to_json(r)::text),'' ORDER BY id)) AS value FROM editor.reviews r WHERE generation_id=%s",(generation,)).fetchone()['value']
 return {'records_md5':a,'reviews_md5':b}
before=protected();assert before==prior['protected_after'],'ORIGINAL_SOURCE_SNAPSHOT_CHANGED'
with connection() as db:
 assert db.execute("SELECT count(*) AS n FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()['n']==0,'ACTIVE_PRODUCT_JOB'
 spans=db.execute("SELECT id,record_key,data FROM editor.records WHERE generation_id=%s AND kind='source_spans' AND (data->>'pdf_page')::int=%s ORDER BY record_key",(generation,page)).fetchall()
 context=db.execute("SELECT data FROM editor.records WHERE id=%s AND generation_id=%s",(prior['page_purpose']['record_id'],generation)).fetchone()['data']
assert context==prior['page_purpose_source_record']['data']
m=types.ModuleType('semantic_candidate');exec(compile(p['module'],'semantic-candidate.py','exec'),m.__dict__)
assert m.digest(context)==prior['page_purpose']['record_sha256']
candidate=prior['gated_candidates']
for claim in candidate['claims']+candidate['blocked_claims']:
 assert claim['text']==claim['model_candidate']['text'],'CANDIDATE_TEXT_CHANGED'
review=m.review_page(candidate,spans,model,page_purpose=prior['page_purpose'])
after=protected();assert before==after,'SOURCE_OR_REVIEW_CHANGED'
print(json.dumps({'generation_id':generation,'pdf_page':page,'candidate_sha256':m.digest(candidate),
 'semantic_module_sha256':hashlib.sha256(p['module'].encode()).hexdigest(),
 'protected_before':before,'protected_after':after,'review':review,
 'application_writes':0,'semantic_acceptance':False},ensure_ascii=False))
'''
raw=subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],cwd=root,input=json.dumps(payload).encode())
result=json.loads(raw)
with out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({'evidence':str(out),'eligible':sum(v['eligible_for_synthesis'] for v in result['review']['claims']),
                 'reasons':[v['reason'] for v in result['review']['claims']],'application_writes':0}))
