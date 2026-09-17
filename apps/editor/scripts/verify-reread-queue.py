#!/usr/bin/env python3
"""Real queue component acceptance. No analysis, source, or review DB writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid

p=argparse.ArgumentParser()
p.add_argument('--base',required=True)
p.add_argument('--generation',required=True,type=uuid.UUID)
p.add_argument('--pages',required=True,type=int,nargs='+')
p.add_argument('--wait-seconds',type=int,default=900)
a=p.parse_args();assert len(set(a.pages))==len(a.pages) and all(x>0 for x in a.pages)
root=Path(__file__).resolve().parents[1];os.chdir(root);gen=str(a.generation)
token=(root/'secrets/api_token').read_text().strip()
def sql(q):
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres',
        'psql','-U','postgres','-d','editor','-Atc',q],text=True))
def database(kind):
    return sql("SELECT coalesce(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='"+gen+"' AND kind='"+kind+"'")
def get_records(kind):
    rows=[]
    while True:
        with urllib.request.urlopen(urllib.request.Request(a.base.rstrip('/')+f'/v1/generations/{gen}/{kind}?offset={len(rows)}&limit=100',headers={'Authorization':'Bearer '+token}),timeout=60) as r:b=json.load(r)
        rows.extend(b['items'])
        if not b['has_more']:return rows
        assert b['items']
def state():
    return sql("SELECT json_build_object('jobs',(SELECT count(*) FROM editor.jobs),'generations',(SELECT count(*) FROM editor.generations),'reviews',(SELECT coalesce(json_agg(to_jsonb(r) ORDER BY r.id),'[]'::json) FROM editor.reviews r WHERE generation_id='"+gen+"'),'generation',(SELECT to_jsonb(g) FROM editor.generations g WHERE id='"+gen+"'))")
before_state=state();before={kind:database(kind) for kind in ('source_spans','evidence')}
for kind in before:assert get_records(kind)==before[kind],kind+'_API_PG_MISMATCH'
selected=[r for r in before['source_spans'] if r['data']['pdf_page'] in a.pages]
evidence={r['data']['pdf_page']:r for r in before['evidence'] if r['data']['pdf_page'] in a.pages}
assert set(evidence)==set(a.pages) and all(any(r['data']['pdf_page']==page for r in selected) for page in a.pages)
runner=r'''
import hashlib,io,json,math,sys
from pathlib import Path
from PIL import Image,ImageOps
from editor.reread_queue import submit,await_result,load_verified,QUEUE,SOURCE,artifact_report,artifact_directory
p=json.load(sys.stdin);reports=[]
def h(raw):return hashlib.sha256(raw).hexdigest()
def snapshot(request):
 rid=request['request_id'];result=QUEUE/'results'/(rid+'.json');path=artifact_report(request)
 return {'request_sha256':h((QUEUE/'requests'/(rid+'.json')).read_bytes()),'result_sha256':h(result.read_bytes()),
         'artifact_sha256':h(path.read_bytes()),'attempt_count':len(list((QUEUE/'attempts'/rid).glob('*.json')))}
for page in p['pages']:
 evidence=p['evidence'][str(page)];d=evidence['data'];rows=[r for r in p['rows'] if r['data']['pdf_page']==page]
 assert all(r['data']['render_sha256']==d['ocr_render_sha256'] for r in rows)
 regions=[{'region_key':r['id'],'bbox':r['data']['bbox']} for r in rows]
 def check_source():
  root=SOURCE/d['source_sha256'];manifest=json.loads((root/'manifest.json').read_text())
  assert manifest['sha256']==d['source_sha256'] and page<=manifest['pdf_pages']
  assert h((root/'ocr-regions-v2'/f'page-{page:04}.png').read_bytes())==d['ocr_render_sha256']
 request=submit(p['generation'],d['source_sha256'],page,d['ocr_render_sha256'],regions,attempt_token=1)
 measurements,provenance=await_result(request,check_active=check_source,queue_wait_seconds=p['wait'])
 assert load_verified(provenance,evidence)==measurements
 original=(SOURCE/d['source_sha256']/'ocr-regions-v2'/f'page-{page:04}.png').read_bytes()
 image=Image.open(io.BytesIO(original)).convert('RGB');checked=[]
 for index,row in enumerate(rows):
  m=measurements[row['id']];x,y,w,hh=row['data']['bbox'];bounds=[math.floor(x*image.width),math.floor(y*image.height),min(image.width,math.ceil((x+w)*image.width)),min(image.height,math.ceil((y+hh)*image.height))]
  assert bounds==m['crop_pixels'];crop=image.crop(bounds);factor=min(3,max(1,64/crop.height));crop=crop.resize((max(1,round(crop.width*factor)),max(1,round(crop.height*factor))))
  crop=ImageOps.expand(crop,border=16,fill='white');stream=io.BytesIO();crop.save(stream,format='PNG');raw=stream.getvalue()
  assert h(raw)==m['crop_sha256'];directory=artifact_directory(request)/str(index);assert (directory/'crop.png').read_bytes()==raw
  for reading in m['readings']:
   tsv=(directory/('psm'+str(reading['psm'])+'.tsv')).read_bytes();assert h(tsv)==reading['tsv_sha256']
   # Independently read TSV columns using header indices, not producer csv code.
   lines=tsv.decode().splitlines();header=lines[0].split('\t');tokens=[];scores=[]
   for line in lines[1:]:
    fields=line.split('\t',len(header)-1)
    if len(fields)==len(header) and fields[header.index('level')]=='5' and fields[header.index('text')].strip():
     tokens.append(fields[header.index('text')]);scores.append(float(fields[header.index('conf')]))
   assert ' '.join(tokens)==reading['text'] and scores==reading['word_confidences']
  checked.append({'source_span_id':row['id'],'bbox':m['bbox'],'crop_sha256':m['crop_sha256'],
                  'independent_geometry_equal':True,'raw_tsv_text_confidences_equal':True})
 first=snapshot(request)
 again=submit(p['generation'],d['source_sha256'],page,d['ocr_render_sha256'],regions,attempt_token=1)
 repeat,repeat_provenance=await_result(again,check_active=check_source,queue_wait_seconds=p['wait'])
 assert again==request and repeat==measurements and repeat_provenance==provenance and snapshot(again)==first
 reports.append({'pdf_page':page,'regions':len(rows),'request':request,'provenance':provenance,
                 'immutable_replay':first,'same_request_no_extra_attempt':True,'checks':checked})
print(json.dumps(reports))
'''
reports=json.loads(subprocess.check_output(['docker','compose','exec','-T','reread-worker','python','-c',runner],
    input=json.dumps({'generation':gen,'pages':a.pages,'rows':selected,'evidence':evidence,'wait':a.wait_seconds}),text=True,
    timeout=(a.wait_seconds+60)*len(a.pages)))
after={kind:database(kind) for kind in before};after_state=state()
assert before==after and before_state==after_state,'SOURCE_REVIEW_OR_JOB_STATE_CHANGED'
for kind in after:assert get_records(kind)==after[kind]
report={'status':'PASS','at':datetime.now(timezone.utc).isoformat(),'api':a.base,'generation_id':gen,'pages':a.pages,
    'regions':len(selected),'database':'real isolated Editor PostgreSQL','api_pg_equal':True,'source_records_unchanged':True,
    'source_records_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
    'jobs_generations_reviews_metadata_unchanged':True,'before_state':before_state,'after_state':after_state,
    'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'page_reports':reports,
    'source_or_review_writes':0,'semantic_acceptance':False,'product_optical_end_to_end':False,'fence_cancellation_tested':False}
out=root/'evidence'/('reread-queue-component-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ('page_reports','before_state','after_state')}|{'evidence':str(out)},indent=2))
