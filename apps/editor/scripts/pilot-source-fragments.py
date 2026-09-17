#!/usr/bin/env python3
"""Run on deployment host only, real API/PG source; writes evidence, never DB."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import uuid

p=argparse.ArgumentParser()
p.add_argument('generation');p.add_argument('--page',type=int,required=True)
p.add_argument('--span-id');p.add_argument('--module',required=True)
p.add_argument('--root',default='/data/nanobaseai/editor');args=p.parse_args()
root=Path(args.root);gen=str(uuid.UUID(args.generation));module=Path(args.module).read_text()
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
def api(path):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8810'+path,headers=headers),timeout=30) as r:return json.load(r)
rows=[];offset=0
while True:
    result=api(f'/v1/generations/{gen}/source_spans?pdf_page={args.page}&limit=100&offset={offset}')
    rows+=result['items']
    if not result['has_more']:break
    offset+=len(result['items'])
if args.span_id:rows=[r for r in rows if r['id']==str(uuid.UUID(args.span_id))]
assert rows,'NO_SOURCE_ROWS'
def execute(service,code,input_text):
    return subprocess.check_output(['docker','compose','exec','-T',service,'python','-c',code],input=input_text.encode(),cwd=root).decode()
code="import sys,json; from editor.config import connection; payload=json.load(sys.stdin); db=connection(); c=db.__enter__(); rows=c.execute('SELECT id,record_key,data FROM editor.records WHERE generation_id=%s AND kind=%s AND data->>%s=%s',(payload['generation'],'source_spans','pdf_page',str(payload['page']))).fetchall(); print(json.dumps(rows,default=str))"
pg=json.loads(execute('api',code,json.dumps({'generation':gen,'page':args.page})))
by_id={r['id']:r for r in pg}
assert all(r['data']==by_id[r['id']]['data'] and r['record_key']==by_id[r['id']]['record_key'] for r in rows),'API_PG_MISMATCH'
claims=api(f'/v1/generations/{gen}/page_claims?pdf_page={args.page}&limit=100')['items']
assert len(claims)==1,'PAGE_ROLE_NOT_AVAILABLE'
code="import sys,json; from editor.config import connection; p=json.load(sys.stdin); db=connection(); c=db.__enter__(); row=c.execute('SELECT data FROM editor.records WHERE generation_id=%s AND id=%s',(p['generation'],p['id'])).fetchone(); print(json.dumps(row['data']))"
claim_pg=json.loads(execute('api',code,json.dumps({'generation':gen,'id':claims[0]['id']})))
assert claim_pg==claims[0]['data'],'PAGE_ROLE_API_PG_MISMATCH'
page_role=claim_pg.get('page_role','UNKNOWN')
source_code="from editor.book_store import source_for; import json; print(json.dumps(source_for("+repr(gen)+"),default=str))"
source=json.loads(execute('api',source_code,''))
payload={'rows':rows,'source':source}
tail="\npayload=json.loads("+repr(json.dumps(payload))+ "); output=[]\nfor row in payload['rows']:\n for candidate in propose(row):\n  path=Path('/data/artifacts')/payload['source']['sha256']/'ocr-regions-v2'/('page-%04d.png'%row['data']['pdf_page'])\n  output.append({'row':row,'measurement':measure_tesseract(path.read_bytes(),row,candidate)})\nprint(json.dumps(output))\n"
measured=json.loads(execute('reread-worker','import sys; exec(compile(sys.stdin.read(),"fragment_candidate.py","exec"))',module+tail))
fragments=[]
for item in measured:
    # Existing networked API container calls unchanged OCR service. The offline
    # rereader above retains its network isolation.
    code="import sys,json,time,httpx; p=json.load(sys.stdin); c=httpx.Client(timeout=180,trust_env=False); response=None\nfor attempt in range(7):\n response=c.post('http://ocr:8080/ocr',json={'image_base64':p['crop_image_base64'],'regional_pass':True})\n if response.status_code not in (429,503): break\n time.sleep(min(8,2**attempt))\nresponse.raise_for_status(); print(response.text)"
    raw=execute('api',code,json.dumps(item['measurement'])).strip()
    decision_input={'row':item['row'],'measurement':item['measurement'],'paddle_raw':raw}
    tail="\np=json.loads("+repr(json.dumps(decision_input))+ "); print(json.dumps(decide(p['row'],p['measurement'],p['paddle_raw'])))"
    decision=json.loads(execute('api','import sys; exec(compile(sys.stdin.read(),"fragment_candidate.py","exec"))',module+tail))
    if decision['data']['measurement']['blockers']==['QUOTE_OR_PUNCTUATION_DISAGREEMENT']:
        code="import sys,json,os,httpx,hashlib; p=json.load(sys.stdin); payload={'model':os.environ.get('EDITOR_OCR_VL_MODEL','paddleocr-vl-1.6'),'temperature':0,'max_tokens':256,'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,'+p['crop_image_base64']}},{'type':'text','text':'OCR:'}]}]}; raw=json.dumps(payload,separators=(',',':')).encode(); c=httpx.Client(timeout=900,trust_env=False); r=c.post(os.environ['EDITOR_OCR_VL_BASE_URL'].rstrip('/')+'/v1/chat/completions',content=raw,headers={'Content-Type':'application/json'}); r.raise_for_status(); print(json.dumps({'raw':r.text,'request_sha256':hashlib.sha256(raw).hexdigest(),'model_revision':os.environ.get('EDITOR_OCR_VL_REVISION')}))"
        vl=json.loads(execute('api',code,json.dumps(item['measurement'])))
        decision_input.update(vl_raw=vl['raw'])
        decision_input['measurement'].update(vl_request_sha256=vl['request_sha256'],vl_model_revision=vl['model_revision'])
        tail="\np=json.loads("+repr(json.dumps(decision_input))+ "); print(json.dumps(decide(p['row'],p['measurement'],p['paddle_raw'],p['vl_raw'])))"
        decision=json.loads(execute('api','import sys; exec(compile(sys.stdin.read(),"fragment_candidate.py","exec"))',module+tail))
    fragments.append(decision)
tail="\nfrom editor.text_attribution import extract\nrows=json.loads("+repr(json.dumps(fragments))+ "); print(json.dumps(extract(rows,"+repr(page_role)+")))"
attributions=json.loads(execute('api','import sys; exec(compile(sys.stdin.read(),"fragment_candidate.py","exec"))',module+tail))
report={'generation_id':gen,'pdf_page':args.page,'source_sha256':source['sha256'],
        'api_pg_match':True,'parent_rows':len(rows),'module_sha256':hashlib.sha256(module.encode()).hexdigest(),
        'fragments':fragments,'attributions':attributions,'application_writes':0,'semantic_acceptance':False,
        'page_role_for_extraction':page_role,'page_role_source_record_id':claims[0]['id']}
target=root/'evidence'/('source-fragments-'+gen+'-page-%04d-'%args.page+report['module_sha256'][:12]+'.json')
with target.open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2)
print(json.dumps({'evidence':str(target),'fragments':len(fragments),'agreed':sum(r['data']['status']=='TEXT_AGREED' for r in fragments),'attributions':attributions,'semantic_acceptance':False},ensure_ascii=False))
