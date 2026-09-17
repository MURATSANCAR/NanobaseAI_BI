#!/usr/bin/env python3
"""Real first-book optical canary, stopped after the requested source page."""
import argparse,hashlib,json,os,re,subprocess,time,urllib.error,urllib.request,uuid
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--database',required=True)
p.add_argument('--content-version',required=True,type=uuid.UUID);p.add_argument('--priority-page',required=True,type=int)
p.add_argument('--worker-service',required=True);p.add_argument('--timeout',type=int,default=1200)
a=p.parse_args();assert re.fullmatch('[a-zA-Z0-9_]+',a.database) and 'canary' in a.worker_service and re.fullmatch('[a-z0-9-]+',a.worker_service)
assert 1<=a.timeout<=3600 and a.priority_page>0
root=Path(__file__).resolve().parents[1];os.chdir(root);cv=str(a.content_version);token=(root/'secrets/api_token').read_text().strip()
out=root/'evidence'/('automatic-reread-'+a.database+'-'+cv+'.json');out.parent.mkdir(exist_ok=True)
report=json.loads(out.read_text()) if out.exists() else {'status':'STARTED','api':a.base,'database':a.database,'content_version_id':cv,
 'priority_page':a.priority_page,'idempotency_key':'automatic-reread:'+str(uuid.uuid4()),'started_at':datetime.now(timezone.utc).isoformat(),
 'semantic_acceptance':False,'book_complete':False,'fence_cancellation_verification':'PARTIAL','source_or_review_manual_writes':0}
assert report['api']==a.base and report['database']==a.database and report['priority_page']==a.priority_page
def save():out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
def sql(q):return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d',a.database,'-Atc',q],text=True))
def call(method,path,body=None,key=None):
 headers={'Authorization':'Bearer '+token}
 if key:headers['Idempotency-Key']=key
 if body is not None:body=json.dumps(body).encode();headers['Content-Type']='application/json'
 for attempt in range(7):
  try:
   with urllib.request.urlopen(urllib.request.Request(a.base.rstrip('/')+path,data=body,headers=headers,method=method),timeout=60) as response:return json.load(response)
  except (urllib.error.URLError,TimeoutError) as exc:
   if isinstance(exc,urllib.error.HTTPError) and exc.code not in (502,503,504):raise
   if attempt==6:raise
   time.sleep(min(2**attempt,10))
def records(kind,page=None):
 items=[]
 while True:
  b=call('GET',f"/v1/generations/{report['generation_id']}/{kind}?offset={len(items)}&limit=100"+(f'&pdf_page={page}' if page is not None else ''))
  items.extend(b['items'])
  if not b['has_more']:return items
def old_state(exclude=None):
 where=" WHERE generation_id!='"+exclude+"'" if exclude else ''
 return sql("SELECT json_build_object('content',(SELECT to_jsonb(c) FROM editor.content_versions c WHERE id='"+cv+"'),'old_records_md5',(SELECT md5(coalesce(string_agg(id::text||data::text,'' ORDER BY id),'')) FROM editor.records"+where+"),'reviews',(SELECT coalesce(json_agg(to_jsonb(r) ORDER BY id),'[]'::json) FROM editor.reviews r))")
def stop():
 if report.get('job_id'):
  report['cancel_response']=call('POST','/v1/jobs/'+report['job_id']+'/cancel',{'purpose':'validation'},report['idempotency_key']+':cancel');save()
  subprocess.run(['docker','compose','stop','-t','5',a.worker_service],check=True,capture_output=True)
  report['stopped_worker_service']=a.worker_service;save()
save();begin=time.monotonic()
try:
 source=sql("SELECT json_build_object('sha',c.sha256,'manifest',s.manifest) FROM editor.content_versions c JOIN editor.source_probes s ON s.sha256=c.sha256 WHERE c.id='"+cv+"'")
 assert a.priority_page<=source['manifest']['pdf_pages']
 if 'before' not in report:
  assert sql("SELECT count(*) FROM editor.generations WHERE content_version_id='"+cv+"'")==0,'CONTENT_ALREADY_ANALYZED'
  original_hash=subprocess.check_output(['docker','compose','exec','-T','reread-worker','python','-c',
   "import hashlib,sys;from pathlib import Path;p=Path('/data/artifacts')/sys.argv[1]/'original.pdf';print(hashlib.sha256(p.read_bytes()).hexdigest())",source['sha']],text=True).strip()
  assert original_hash==source['sha']
  report['before']=old_state();report['source_sha256']=source['sha'];report['original_pdf_sha256_before']=original_hash;save()
 if 'generation_id' not in report:
  result=call('POST','/v1/content-versions/'+cv+'/analyses',{'purpose':'validation','priority_pages':[a.priority_page]},report['idempotency_key'])
  report.update(result);save()
 gen=str(uuid.UUID(report['generation_id']))
 manifest=sql("SELECT manifest FROM editor.generations WHERE id='"+gen+"'");assert manifest.get('reuse_measurements_from') is None
 report['generation_manifest']=manifest;report.setdefault('observed_progress',[])
 deadline=time.monotonic()+a.timeout
 while True:
  readings=records('page_readings',a.priority_page)
  if readings:break
  job=call('GET','/v1/jobs/'+report['job_id']);progress=job.get('progress',{})
  if progress and (not report['observed_progress'] or report['observed_progress'][-1]!=progress):report['observed_progress'].append(progress);save()
  if job['status'] in ('FAILED','CANCELLED','COMPLETED'):raise RuntimeError('CANARY_ENDED_BEFORE_OPTICAL:'+job['status'])
  if time.monotonic()>deadline:raise RuntimeError('CANARY_OPTICAL_TIMEOUT')
  time.sleep(.5)
 stop()
 rows={kind:records(kind,a.priority_page) for kind in ('source_spans','evidence','page_readings')}
 for kind,items in rows.items():
  db=sql("SELECT coalesce(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='"+gen+"' AND kind='"+kind+"' AND (data->>'pdf_page')::int="+str(a.priority_page))
  assert items==db,kind+'_API_PG_MISMATCH'
 generated=[r for r in rows['source_spans'] if r['data'].get('reread_generated_in_generation') is True]
 assert generated and len(rows['page_readings'])==len(rows['evidence'])==1
 assert rows['page_readings'][0]['data']['span_count']==len(rows['source_spans'])
 assert rows['page_readings'][0]['data']['measurement_reused'] is False
 runner=r'''
import csv,hashlib,io,json,math,sys
from pathlib import Path
from PIL import Image,ImageOps
from editor.reread_queue import load_verified,artifact_directory
p=json.load(sys.stdin);e=p['evidence'];d=e['data'];base=Path('/data/artifacts')/d['source_sha256']
def h(b):return hashlib.sha256(b).hexdigest()
assert h((base/'original.pdf').read_bytes())==d['source_sha256']
manifest=json.loads((base/'manifest.json').read_text());assert manifest['sha256']==d['source_sha256'] and d['pdf_page']<=manifest['pdf_pages']
raw=(base/'ocr-regions-v2'/f"page-{d['pdf_page']:04}.png").read_bytes();assert h(raw)==d['ocr_render_sha256'];im=Image.open(io.BytesIO(raw)).convert('RGB')
results=[];seen={}
for row in p['rows']:
 s=row['data'];prov=s['reread_provenance'];key=prov['request_id']
 if key not in seen:
  measured=load_verified(prov,e);report=json.loads(Path(prov['artifact_path']).read_text());req=report['request'];assert req['generation_id']==p['generation']
  assert all(set(r)=={'region_key','bbox'} for r in req['regions']);seen[key]=(measured,req)
 measured,req=seen[key];m=measured[row['id']];assert m==s['reread_measurement'] and m['bbox']==s['bbox']
 x,y,w,hh=s['bbox'];bounds=[math.floor(x*im.width),math.floor(y*im.height),min(im.width,math.ceil((x+w)*im.width)),min(im.height,math.ceil((y+hh)*im.height))];assert bounds==m['crop_pixels']
 crop=im.crop(bounds);factor=min(3,max(1,64/crop.height));crop=crop.resize((max(1,round(crop.width*factor)),max(1,round(crop.height*factor))))
 crop=ImageOps.expand(crop,border=16,fill='white');stream=io.BytesIO();crop.save(stream,format='PNG');assert h(stream.getvalue())==m['crop_sha256']
 index=[r['region_key'] for r in req['regions']].index(row['id']);folder=artifact_directory(req)/str(index)
 for reading in m['readings']:
  rawtsv=(folder/('psm'+str(reading['psm'])+'.tsv')).read_bytes();assert h(rawtsv)==reading['tsv_sha256']
  lines=rawtsv.decode().splitlines();headers=lines[0].split('\t');words=[];conf=[]
  for line in lines[1:]:
   v=line.split('\t',len(headers)-1)
   if len(v)==len(headers) and v[headers.index('level')]=='5' and v[headers.index('text')].strip():words.append(v[headers.index('text')]);conf.append(float(v[headers.index('conf')]))
  assert ' '.join(words)==reading['text'] and conf==reading['word_confidences']
 results.append({'source_span_id':row['id'],'crop_sha256':m['crop_sha256'],'independent_crop_tsv_equal':True})
print(json.dumps({'original_pdf_sha256':h((base/'original.pdf').read_bytes()),'request_ids':list(seen),'generated_regions':len(results),'checks':results}))
'''
 proof=json.loads(subprocess.check_output(['docker','compose','exec','-T','reread-worker','python','-c',runner],input=json.dumps({'evidence':rows['evidence'][0],'rows':generated,'generation':gen}),text=True))
 assert proof['original_pdf_sha256']==report['source_sha256']==report['original_pdf_sha256_before'];assert old_state(gen)==report['before'],'PREEXISTING_DATA_CHANGED'
 report['post_optical_records']=sql("SELECT coalesce(json_object_agg(kind,n),'{}'::json) FROM (SELECT kind,count(*) n FROM editor.records WHERE generation_id='"+gen+"' AND kind IN ('visual_observations','page_claims','page_checks') GROUP BY kind) s")
 report['model_request_not_started_proven']=False
 report.update(status='PASS',optical_automatic_first_book=True,parent_none=True,api_pg_equal=True,
  generated_regions=len(generated),total_page_spans=len(rows['source_spans']),artifact_proof=proof,
  old_data_unchanged=True,source_rows=rows,final_job=call('GET','/v1/jobs/'+report['job_id']),
  elapsed_seconds=round(time.monotonic()-begin,3),finished_at=datetime.now(timezone.utc).isoformat(),
  verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
 save();print(json.dumps({k:v for k,v in report.items() if k not in ('before','source_rows','artifact_proof')}|{'evidence':str(out)},indent=2))
except Exception as exc:
 report['status']='FAILED';report['error']=str(exc);save()
 try:stop()
 except Exception as cleanup:report['cleanup_error']=str(cleanup);save()
 raise
