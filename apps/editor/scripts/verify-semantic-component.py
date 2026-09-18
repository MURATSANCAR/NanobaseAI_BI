#!/usr/bin/env python3
"""Remote real API/PG/model component acceptance, without application writes."""
import json,subprocess,urllib.request,hashlib,base64,sys,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1]; gen=str(uuid.UUID(sys.argv[1]));page=int(sys.argv[2])
if page < 1: raise SystemExit('Page must be positive')
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
rows={}
for kind in ('page_claims','source_spans'):
 items=[];offset=0
 while True:
  request=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{gen}/{kind}?pdf_page={page}&offset={offset}&limit=100',headers=headers)
  with urllib.request.urlopen(request,timeout=30) as response: result=json.load(response)
  items+=result['items']
  if not result['has_more']:break
  offset+=len(result['items'])
 rows[kind]=items
module=Path(sys.argv[3]).read_text() if len(sys.argv)>3 else (root/'backend/editor/semantic_acceptance.py').read_text()
reading_module=Path(sys.argv[4]).read_text() if len(sys.argv)>4 else ''
payload={'rows':rows,'module':module,'reading_module':reading_module,'generation':gen,'page':page}
code='''import sys,json,hashlib,types,inspect
from editor.config import connection,code_manifest
from editor.analysis import model
p=json.load(sys.stdin)
with connection() as db:
 rows=db.execute("SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s AND data->>'pdf_page'=%s AND kind IN ('page_claims','source_spans')",(p['generation'],str(p['page']))).fetchall()
by_id={str(r['id']):r for r in rows}
assert sum(map(len,p['rows'].values()))==len(rows),'API_PG_COUNT_MISMATCH'
for kind,items in p['rows'].items():
 for r in items:
  d=by_id[r['id']];assert d['kind']==kind and d['record_key']==r['record_key'] and d['data']==r['data'],'API_PG_MISMATCH'
if p['reading_module']:
 reader=types.ModuleType('editor.source_unit_claims');exec(compile(p['reading_module'],'candidate-reading.py','exec'),reader.__dict__)
 sys.modules['editor.source_unit_claims']=reader
module=types.ModuleType('semantic_candidate');exec(compile(p['module'],'candidate-semantic.py','exec'),module.__dict__)
page=p['rows']['page_claims'][0]['data']; review=module.review_page(page,p['rows']['source_spans'],model)
print(json.dumps({'stage':'review','review':review},ensure_ascii=False),flush=True)
extra={'source_spans':p['rows']['source_spans']} if 'source_spans' in inspect.signature(module.synthesize_reviewed).parameters else {}
synthesis=module.synthesize_reviewed([page],[review],model,**extra)
print(json.dumps({'stage':'complete','generation_id':p['generation'],'pdf_page':p['page'],'api_pg_match':True,'application_writes':0,'candidate_code_sha256':hashlib.sha256(p['module'].encode()).hexdigest(),'reading_code_sha256':hashlib.sha256(p['reading_module'].encode()).hexdigest() if p['reading_module'] else None,'runtime_code_manifest':code_manifest(),'review':review,'synthesis':synthesis},ensure_ascii=False),flush=True)
'''
out=root/f'evidence/semantic-live-component-{gen}-page{page:04}-{hashlib.sha256((module+reading_module).encode()).hexdigest()[:12]}.jsonl'
if out.exists(): raise SystemExit('Evidence already exists; preserve it and choose a new generation')
with out.open('w') as target:
 proc=subprocess.run(['docker','compose','exec','-T','api','python','-u','-c',code],input=json.dumps(payload),text=True,stdout=target,stderr=subprocess.PIPE,cwd=root)
print(json.dumps({'returncode':proc.returncode,'evidence':str(out),'stderr':proc.stderr}))
if proc.returncode: raise SystemExit(proc.returncode)
report=json.loads(out.read_text().splitlines()[-1]);print(json.dumps({'api_pg_match':report['api_pg_match'],'model_supported':report['review']['machine_supported_count'],'synthesis_statements':len(report['synthesis']['statements']),'application_writes':0}))
