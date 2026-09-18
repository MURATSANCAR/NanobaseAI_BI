#!/usr/bin/env python3
"""Remote read-only real API/PostgreSQL cross-page attribution acceptance."""
import json,subprocess,urllib.request,hashlib,sys,uuid,os
from pathlib import Path
root=Path(__file__).resolve().parents[1];gen=str(uuid.UUID(sys.argv[1]))
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
rows={}
requested_kinds=['evidence','source_spans','layout_regions','visual_observations','page_claims']
if os.environ.get('EDITOR_VERIFY_PERSISTED_CONTEXT')=='1':
 requested_kinds+=['source_fragments','page_context_roles']
for kind in requested_kinds:
 items=[];offset=0
 while True:
  request=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{gen}/{kind}?offset={offset}&limit=100',headers=headers)
  with urllib.request.urlopen(request,timeout=30) as response:result=json.load(response)
  items+=result['items']
  if not result['has_more']:break
  offset+=len(result['items'])
 rows[kind]=items
code='''import sys,json,types,hashlib
from editor.config import connection
p=json.load(sys.stdin)
with connection() as db:
 rows=db.execute("SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s AND kind=ANY(%s)",(p['gen'],list(p['rows']))).fetchall()
by_id={str(r['id']):r for r in rows}
assert len(by_id)==sum(map(len,p['rows'].values())),'API_PG_COUNT_MISMATCH'
for kind,items in p['rows'].items():
 for r in items:
  d=by_id[r['id']];assert d['kind']==kind and d['record_key']==r['record_key'] and d['data']==r['data'],'API_PG_MISMATCH'
indexes={kind:{r['data']['pdf_page']:r for r in items} for kind,items in p['rows'].items() if kind not in ('source_spans','source_fragments','page_context_roles')}
assert indexes['evidence'] and all(set(index)==set(indexes['evidence']) for index in indexes.values()),'SOURCE_PAGE_COVERAGE_INCOMPLETE'
bundles=[]
for page in sorted(set.intersection(*(set(v) for v in indexes.values()))):
 bundles.append({'evidence':indexes['evidence'][page],'layout':indexes['layout_regions'][page]['data'],'visual':indexes['visual_observations'][page]['data'],'page_role':indexes['page_claims'][page]['data']['page_role'],'spans':[r for r in p['rows']['source_spans'] if r['data']['pdf_page']==page]})
 if 'source_fragments' in p['rows']:
  context=next((r for r in p['rows']['page_context_roles'] if r['data']['pdf_page']==page),None)
  bundles[-1].update(fragments=[r for r in p['rows']['source_fragments'] if r['data']['pdf_page']==page],
                    context_role=context['data'] if context else None,
                    context_role_record_id=context['id'] if context else None)
fragment_report=p.get('fragment_report')
if fragment_report:
 assert fragment_report['generation_id']==p['gen'] and fragment_report['api_pg_match'] is True,'FRAGMENT_REPORT_SCOPE_MISMATCH'
 matched=False
 for bundle in bundles:
  if bundle['evidence']['data']['pdf_page']==fragment_report['pdf_page']:
   assert fragment_report['source_sha256']==bundle['evidence']['data']['source_sha256'],'FRAGMENT_SOURCE_MISMATCH'
   assert fragment_report['page_role_for_extraction']==bundle['page_role'],'FRAGMENT_PAGE_ROLE_MISMATCH'
   assert fragment_report['page_role_source_record_id']==indexes['page_claims'][fragment_report['pdf_page']]['id'],'FRAGMENT_ROLE_RECORD_MISMATCH'
   bundle['fragments']=fragment_report['fragments'];matched=True
 assert matched,'FRAGMENT_PAGE_NOT_READY'
context_report=p.get('context_report')
if context_report:
 assert context_report['generation_id']==p['gen'] and context_report['application_writes']==0,'CONTEXT_REPORT_SCOPE_MISMATCH'
 assert context_report['fragment_artifact_sha256']==p.get('fragment_report_sha256'),'CONTEXT_FRAGMENT_ARTIFACT_MISMATCH'
 assert context_report['module_sha256']==hashlib.sha256(p['context_module'].encode()).hexdigest(),'CONTEXT_MODULE_HASH_MISMATCH'
 context_module=types.ModuleType('editor.page_context');exec(compile(p['context_module'],'candidate-pagecontext.py','exec'),context_module.__dict__)
 sys.modules['editor.page_context']=context_module
 projections=context_report.get('fragment_record_id_projection',[])
 if projections:
  from editor.book_store import identifier
  projected_by_measurement={x['measurement_identity']:x for x in projections}
  for bundle in bundles:
   projected=[]
   for fragment in bundle.get('fragments',[]):
    data=fragment['data'];parent=by_id[data['parent_source_span_id']]
    key=parent['record_key']+'-fragment-'+hashlib.sha256(json.dumps(data['bbox'],separators=(',',':')).encode()).hexdigest()[:16]
    expected={'measurement_identity':fragment['id'],'record_key':key,
              'projected_record_id':identifier(p['gen'],'source_fragments',key),'persisted':False}
    assert projected_by_measurement[fragment['id']]==expected,'CONTEXT_FRAGMENT_ID_PROJECTION_MISMATCH'
    projected.append({'id':expected['projected_record_id'],'record_key':key,'data':data})
   bundle['fragments']=projected
 for bundle in bundles:
  if bundle['evidence']['data']['pdf_page']==context_report['target_page']:
   bundle['context_role']=context_report['result']
module=types.ModuleType('cross_page_candidate');exec(compile(p['module'],'candidate-crosspage.py','exec'),module.__dict__)
result=module.resolve(bundles)
# Exercise the actual psycopg UUID types as well as HTTP JSON strings. Keeping
# only API-shaped bundles previously missed a production serialization failure.
def native_row(row):
 original=by_id[row['id']]
 return {key:original[key] for key in ('id','record_key','data')}
native_bundles=[{**bundle,'evidence':native_row(bundle['evidence']),
                'spans':[native_row(row) for row in bundle['spans']]} for bundle in bundles]
if 'source_fragments' in p['rows']:
 for bundle in native_bundles:bundle['fragments']=[native_row(row) for row in bundle.get('fragments',[])]
assert module.resolve(native_bundles)==result,'NATIVE_POSTGRES_API_RESULT_MISMATCH'
print(json.dumps({'gen':p['gen'],'api_pg_match':True,'native_postgres_types_match':True,'application_writes':0,'code_sha256':hashlib.sha256(p['module'].encode()).hexdigest(),'fragment_report_sha256':p.get('fragment_report_sha256'),'context_report_sha256':p.get('context_report_sha256'),'result':result},ensure_ascii=False))
'''
module=Path(sys.argv[2]).read_text() if len(sys.argv)>2 else (root/'backend/editor/cross_page_attribution.py').read_text()
code_hash=hashlib.sha256(module.encode()).hexdigest()
fragment_raw=Path(sys.argv[3]).read_bytes() if len(sys.argv)>3 and sys.argv[3]!='-' else None
fragment_report=json.loads(fragment_raw) if fragment_raw else None
fragment_hash=hashlib.sha256(fragment_raw).hexdigest() if fragment_raw else None
context_raw=Path(sys.argv[4]).read_bytes() if len(sys.argv)>4 else None
context_report=json.loads(context_raw) if context_raw else None
context_hash=hashlib.sha256(context_raw).hexdigest() if context_raw else None
context_module=Path(sys.argv[5]).read_text() if len(sys.argv)>5 else None
if context_report and not context_module:raise SystemExit('Context candidate module required')
suffix='-'+fragment_hash[:12] if fragment_hash else ''
if context_hash:suffix+='-'+context_hash[:12]
if os.environ.get('EDITOR_VERIFY_PERSISTED_CONTEXT')=='1':
 suffix+='-persisted-'+hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()[:12]
out=root/f'evidence/cross-page-attribution-{gen}-{code_hash[:12]}{suffix}.json'
if out.exists(): raise SystemExit('Evidence exists; preserve earlier result')
p=subprocess.run(['docker','compose','exec','-T','api','python','-c',code],input=json.dumps({'gen':gen,'rows':rows,'module':module,'fragment_report':fragment_report,'fragment_report_sha256':fragment_hash,'context_report':context_report,'context_report_sha256':context_hash,'context_module':context_module}),capture_output=True,text=True,cwd=root)
if p.returncode:print(p.stderr);raise SystemExit(p.returncode)
with out.open('x') as target: target.write(p.stdout)
r=json.loads(p.stdout);print(json.dumps({'evidence':str(out),'api_pg':True,'code_sha256':r['code_sha256'],'pages':len(r['result']['input_pages']),'named':r['result']['named_identity_count'],'dialogue_links':r['result']['grounded_dialogue_link_count'],'scope_errors':r['result']['scope_errors'],'links':[{'page':x['pdf_page'],'reason':x['reason']} for x in r['result']['links']]}))
