#!/usr/bin/env python3
"""Remote actual-source component comparison; never edits existing book records."""
import argparse
import hashlib
import json
import os
import socket
import sys
from pathlib import Path
import subprocess
import urllib.request
import uuid

p=argparse.ArgumentParser();p.add_argument('generation');p.add_argument('page',type=int);p.add_argument('module')
p.add_argument('--semantic-module')
p.add_argument('--proposal-only',action='store_true')
args=p.parse_args();gen=str(uuid.UUID(args.generation));root=Path(os.environ.get('EDITOR_VERIFY_ROOT',str(Path(__file__).resolve().parents[1]))).resolve()
assert sys.platform.startswith('linux') and os.environ.get('EDITOR_VERIFY_REMOTE_HOST')==socket.gethostname(),'REMOTE_ACTUAL_ENVIRONMENT_REQUIRED'
module=Path(args.module).read_text();semantic_module=Path(args.semantic_module).read_text() if args.semantic_module else ''
digest=hashlib.sha256((module+semantic_module+str(args.proposal_only)).encode()).hexdigest()
out=root/'evidence'/f'source-unit-claims-{gen}-{args.page:04}-{digest[:12]}.json'
assert not out.exists(),'EVIDENCE_ALREADY_EXISTS'
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()};records={}
for kind in ('evidence','layout_regions','source_spans','source_fragments','page_context_roles','page_claims'):
    rows=[]
    for page in range(max(1,args.page-1),args.page+2):
        offset=0
        while True:
            req=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{gen}/{kind}?pdf_page={page}&limit=100&offset={offset}',headers=headers)
            with urllib.request.urlopen(req,timeout=60) as response:batch=json.load(response)
            rows+=batch['items'];offset+=len(batch['items'])
            if not batch['has_more']:break
            assert batch['items'],'EMPTY_PAGINATION'
    records[kind]=rows
assert len([r for r in records['evidence'] if r['data']['pdf_page']==args.page])==1
code='''import hashlib,json,sys,types
from editor.config import connection,code_manifest
from editor.analysis import model
from editor.source_pipeline import quote_check,negation,narrative_gate
from editor.text_attribution import extract,speaker_for_claim
from editor.semantic_acceptance import review_page
p=json.load(sys.stdin);spans=[r for r in p['records']['source_spans'] if r['data']['pdf_page']==p['page']]
evidence=next(r for r in p['records']['evidence'] if r['data']['pdf_page']==p['page'])
def protected_fingerprint():
 with connection() as db:
  records=db.execute("SELECT md5(string_agg(md5(row_to_json(r)::text),'' ORDER BY id)) AS value FROM editor.records r WHERE generation_id=%s",(p['generation'],)).fetchone()['value']
  reviews=db.execute("SELECT md5(string_agg(md5(row_to_json(r)::text),'' ORDER BY id)) AS value FROM editor.reviews r WHERE generation_id=%s",(p['generation'],)).fetchone()['value']
 return {'records_md5':records,'reviews_md5':reviews}
before=protected_fingerprint()
with connection() as db:
 rows=db.execute("SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s AND (data->>'pdf_page')::int BETWEEN %s AND %s AND kind=ANY(%s)",(p['generation'],max(1,p['page']-1),p['page']+1,list(p['records']))).fetchall()
by_id={str(r['id']):r for r in rows}
assert len(rows)==sum(map(len,p['records'].values()))
for kind,items in p['records'].items():
 for r in items:
  actual=by_id[r['id']];assert actual['kind']==kind and actual['record_key']==r['record_key'] and actual['data']==r['data'],'API_PG_MISMATCH'
m=types.ModuleType('source_unit_claims_candidate');exec(compile(p['module'],'source-unit-claims-candidate.py','exec'),m.__dict__)
sys.modules['editor.source_unit_claims']=m
if p['semantic_module']:
 sm=types.ModuleType('semantic_review_candidate');exec(compile(p['semantic_module'],'semantic-review-candidate.py','exec'),sm.__dict__)
 review_page=sm.review_page
from editor.page_context import story_authority
layouts={r['data']['pdf_page']:r['data'] for r in p['records']['layout_regions']}
bundles=[{'evidence':r,'layout':layouts[r['data']['pdf_page']],
          'spans':[v for v in p['records']['source_spans'] if v['data']['pdf_page']==r['data']['pdf_page']],
          'fragments':[v for v in p['records']['source_fragments'] if v['data']['pdf_page']==r['data']['pdf_page']]}
         for r in p['records']['evidence']]
context=next(r for r in p['records']['page_context_roles'] if r['data']['pdf_page']==p['page'])
purpose=story_authority(p['page'],bundles,context)
if purpose['passed'] or m.VERSION!='source-unit-claims-v4':
 with connection() as db:
  assert db.execute("SELECT count(*) AS n FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()['n']==0,'ACTIVE_PRODUCT_JOB'
if m.VERSION=='source-unit-claims-v4':proposal,metrics=m.propose(p['page'],spans,model,page_purpose=purpose)
else:proposal,metrics=m.propose(p['page'],spans,model)
allowed={str(r['id']):r for r in spans if r['data']['status']=='TEXT_AGREED' and r['data']['role']=='TEXT'}
attributions=extract(spans,proposal['page_role'])['attributions'];accepted=[];blocked=[]
for claim in proposal['claims']:
 refs=claim['span_refs'];selected=[allowed[r] for r in refs]
 gate=quote_check(claim['quote'],selected,spans)
 if gate=='MATCH' and bool(negation(claim['quote']))!=bool(negation(claim['text'])):gate='CLAIM_POLARITY_REQUIRES_REVIEW'
 if claim['kind']=='ENTITY':gate='ENTITY_IDENTITY_REQUIRES_REVIEW'
 gate=narrative_gate(proposal['page_role'],gate)
 speaker=speaker_for_claim(claim,attributions) if gate=='MATCH' else None
 item={**claim,'source_gate':gate,'speaker':speaker['label'] if speaker else None,
       'evidence_refs':[evidence['id']],'eligible_for_synthesis':False,'visual_identity_verified':False}
 (accepted if gate=='MATCH' else blocked).append(item)
candidate={'pdf_page':p['page'],'page_role':proposal['page_role'],'claims':accepted,'blocked_claims':blocked}
review={'claims':[],'component_not_exercised':True} if p['proposal_only'] else review_page(candidate,spans,model,page_purpose=purpose)
after=protected_fingerprint();assert before==after,'SOURCE_OR_REVIEW_RECORDS_CHANGED'
print(json.dumps({'protected_before':before,'protected_after':after,'generation_id':p['generation'],'pdf_page':p['page'],'api_pg_match':True,
 'application_writes':0,'semantic_acceptance':False,'candidate_code_sha256':hashlib.sha256(p['module'].encode()).hexdigest(),
 'runtime_code_manifest':code_manifest(),'semantic_candidate_sha256':hashlib.sha256(p['semantic_module'].encode()).hexdigest() if p['semantic_module'] else None,'original':next(r for r in p['records']['page_claims'] if r['data']['pdf_page']==p['page']),
 'page_purpose':purpose,'page_purpose_source_record':context,'proposal_only':p['proposal_only'],
 'proposal':proposal,'metrics':metrics,'gated_candidates':candidate,'semantic_review':review},ensure_ascii=False))
'''
payload={'generation':gen,'page':args.page,'records':records,'module':module,'semantic_module':semantic_module,'proposal_only':args.proposal_only}
raw=subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],cwd=root,input=json.dumps(payload).encode())
result=json.loads(raw)
with out.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
out.chmod(0o600)
print(json.dumps({'evidence':str(out),'api_pg_match':True,'page':args.page,
    'source_units':len(result['proposal']['source_units']),'page_role':result['proposal']['page_role'],
    'source_gates':[c['source_gate'] for c in result['gated_candidates']['claims']+result['gated_candidates']['blocked_claims']],
    'semantic_reasons':[c['reason'] for c in result['semantic_review']['claims']],
    'eligible_claims':sum(c['eligible_for_synthesis'] for c in result['semantic_review']['claims']),
    'application_writes':0,'semantic_acceptance':False}))
