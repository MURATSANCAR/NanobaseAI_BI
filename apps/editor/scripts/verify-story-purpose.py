#!/usr/bin/env python3
"""Real API/PG page-purpose regression, without application content writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import uuid

p=argparse.ArgumentParser()
for name in ('generation','context-module','semantic-module','context-artifact'):
    p.add_argument('--'+name,required=True)
args=p.parse_args();root=Path(__file__).resolve().parents[1]
gen=str(uuid.UUID(args.generation));artifact_raw=Path(args.context_artifact).read_bytes()
artifact=json.loads(artifact_raw);page=artifact['target_page']
context_code=Path(args.context_module).read_text();semantic_code=Path(args.semantic_module).read_text()
assert artifact['generation_id']==gen and artifact['application_writes']==0
assert artifact['module_sha256']==hashlib.sha256(context_code.encode()).hexdigest()
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
kinds=('evidence','layout_regions','source_spans','source_fragments','page_claims');rows={}
for kind in kinds:
    items=[]
    for n in range(max(1,page-1),page+2):
        offset=0
        while True:
            req=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{gen}/{kind}?pdf_page={n}&offset={offset}&limit=100',headers=headers)
            with urllib.request.urlopen(req,timeout=60) as response:batch=json.load(response)
            items+=batch['items']
            if not batch['has_more']:break
            assert batch['items'],'EMPTY_PAGINATION'
            offset+=len(batch['items'])
    rows[kind]=items
payload={'generation':gen,'page':page,'rows':rows,'context_code':context_code,
         'semantic_code':semantic_code,'artifact':artifact,'artifact_sha256':hashlib.sha256(artifact_raw).hexdigest()}
code='''import sys,json,types,uuid
from editor.config import connection
from editor.analysis import model
p=json.load(sys.stdin)
with connection() as db:
 records=db.execute("SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s AND kind=ANY(%s) AND (data->>'pdf_page')::int BETWEEN %s AND %s",(p['generation'],list(p['rows']),max(1,p['page']-1),p['page']+1)).fetchall()
by_id={str(r['id']):r for r in records}
assert len(by_id)==sum(map(len,p['rows'].values())),'API_PG_COUNT_MISMATCH'
for kind,items in p['rows'].items():
 for row in items:
  actual=by_id[row['id']]
  assert actual['kind']==kind and actual['record_key']==row['record_key'] and actual['data']==row['data'],'API_PG_MISMATCH'
context=types.ModuleType('editor.page_context');exec(compile(p['context_code'],'candidate-context.py','exec'),context.__dict__)
sys.modules['editor.page_context']=context
semantic=types.ModuleType('semantic_candidate');exec(compile(p['semantic_code'],'candidate-semantic.py','exec'),semantic.__dict__)
layouts={r['data']['pdf_page']:r['data'] for r in p['rows']['layout_regions']}
bundles=[{'evidence':r,'layout':layouts[r['data']['pdf_page']],
 'spans':[s for s in p['rows']['source_spans'] if s['data']['pdf_page']==r['data']['pdf_page']],
 'fragments':[s for s in p['rows']['source_fragments'] if s['data']['pdf_page']==r['data']['pdf_page']]} for r in p['rows']['evidence']]
assert context.digest(bundles)==p['artifact']['input_bundles_sha256'],'CLASSIFICATION_SOURCE_CHANGED'
authority=context.story_authority(p['page'],bundles,{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'editor-component:'+p['artifact_sha256'])),'data':p['artifact']['result']})
assert authority['reason']!='PAGE_PURPOSE_SOURCE_SCOPE_INVALID','CLASSIFICATION_SCOPE_INVALID'
page=next(r['data'] for r in p['rows']['page_claims'] if r['data']['pdf_page']==p['page'])
spans=[s for s in p['rows']['source_spans'] if s['data']['pdf_page']==p['page']]
review=semantic.review_page(page,spans,model,page_purpose=authority)
synthesis=semantic.synthesize_reviewed([page],[review],model,source_spans=spans)
print(json.dumps({'generation_id':p['generation'],'pdf_page':p['page'],'api_pg_match':True,
 'api_pg_rows':len(records),'application_writes':0,'semantic_acceptance':False,
 'classification_artifact_sha256':p['artifact_sha256'],'candidate_context_record_persisted':False,
 'page_purpose':authority,'review':review,'synthesis':synthesis},ensure_ascii=False))
'''
fingerprint=hashlib.sha256((context_code+semantic_code+payload['artifact_sha256']).encode()).hexdigest()
out=root/'evidence'/f'story-purpose-{gen}-{page:04}-{fingerprint[:12]}.json'
with out.open('x') as target:
    result=subprocess.run(['docker','compose','exec','-T','api','python','-c',code],input=json.dumps(payload),
                          text=True,stdout=target,stderr=subprocess.PIPE,cwd=root)
if result.returncode:raise RuntimeError(result.stderr)
report=json.loads(out.read_text())
print(json.dumps({'evidence':str(out),'api_pg_match':True,'page_purpose':report['page_purpose'],
    'eligible_claims':sum(v['eligible_for_synthesis'] for v in report['review']['claims']),
    'synthesis_statements':len(report['synthesis']['statements']),'application_writes':0},ensure_ascii=False))
