#!/usr/bin/env python3
"""Remote read-only real API/PostgreSQL cross-page attribution acceptance."""
import json,subprocess,urllib.request,hashlib,sys,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1];gen=str(uuid.UUID(sys.argv[1]))
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
rows={}
for kind in ('evidence','source_spans','layout_regions','visual_observations','page_claims'):
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
indexes={kind:{r['data']['pdf_page']:r for r in items} for kind,items in p['rows'].items() if kind!='source_spans'}
bundles=[]
for page in sorted(set.intersection(*(set(v) for v in indexes.values()))):
 bundles.append({'evidence':indexes['evidence'][page],'layout':indexes['layout_regions'][page]['data'],'visual':indexes['visual_observations'][page]['data'],'page_role':indexes['page_claims'][page]['data']['page_role'],'spans':[r for r in p['rows']['source_spans'] if r['data']['pdf_page']==page]})
module=types.ModuleType('cross_page_candidate');exec(compile(p['module'],'candidate-crosspage.py','exec'),module.__dict__)
result=module.resolve(bundles)
print(json.dumps({'gen':p['gen'],'api_pg_match':True,'application_writes':0,'code_sha256':hashlib.sha256(p['module'].encode()).hexdigest(),'result':result},ensure_ascii=False))
'''
module=Path(sys.argv[2]).read_text() if len(sys.argv)>2 else (root/'backend/editor/cross_page_attribution.py').read_text()
code_hash=hashlib.sha256(module.encode()).hexdigest()
out=root/f'evidence/cross-page-attribution-{gen}-{code_hash[:12]}.json'
if out.exists(): raise SystemExit('Evidence exists; preserve earlier result')
p=subprocess.run(['docker','compose','exec','-T','api','python','-c',code],input=json.dumps({'gen':gen,'rows':rows,'module':module}),capture_output=True,text=True,cwd=root)
if p.returncode:print(p.stderr);raise SystemExit(p.returncode)
with out.open('x') as target: target.write(p.stdout)
r=json.loads(p.stdout);print(json.dumps({'evidence':str(out),'api_pg':True,'code_sha256':r['code_sha256'],'pages':len(r['result']['input_pages']),'named':r['result']['named_identity_count'],'scope_errors':r['result']['scope_errors'],'links':[{'page':x['pdf_page'],'reason':x['reason']} for x in r['result']['links']]}))
