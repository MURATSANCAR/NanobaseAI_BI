"""Independent read-only artifact checks; no production module imports."""
import json
import subprocess


def verify_artifacts(spans, evidence, generation):
    program = r'''
import csv,hashlib,io,json,pathlib,sys,uuid
p=json.load(sys.stdin);e=p['evidence'];root=pathlib.Path('/data/artifacts')
digest=lambda b:hashlib.sha256(b).hexdigest()
assert len(e['source_sha256'])==64 and all(c in '0123456789abcdef' for c in e['source_sha256'])
source=root/e['source_sha256'];page=int(e['pdf_page']);assert page>0
render=source/'ocr-regions-v2'/f'page-{page:04}.png'
assert digest(render.read_bytes())==e['ocr_render_sha256']
assert digest((source/'original.pdf').read_bytes())==e['source_sha256']
ocr_raw=(source/'ocr-regions-v2'/f'page-{page:04}.json').read_bytes()
assert digest(ocr_raw)==e['ocr_artifact_sha256']
ocr=json.loads(ocr_raw);assert ocr['source_sha256']==e['source_sha256'] and ocr['pdf_page']==page
assert digest((source/'ocr-regions-v2'/f'page-{page:04}.tsv').read_bytes())==ocr['raw_tsv_sha256']
native_raw=(source/'pdf-text-regions-v1'/f'page-{page:04}.json').read_bytes()
native=json.loads(native_raw);assert native['source_sha256']==e['source_sha256'] and native['pdf_page']==page
reports={};checked=0
for row in p['spans']:
 d=row['data'];assert d['render_sha256']==e['ocr_render_sha256'] and d['pdf_page']==page
 assert d['pdf_artifact_sha256']==digest(native_raw)
 measurement=d.get('reread_measurement');prov=d.get('reread_provenance');generated=d.get('reread_generated_in_generation',False)
 if not measurement:assert not generated;continue
 if prov['method']!='region-reread-queue-v1':assert not generated;continue
 origin=str(uuid.UUID(prov['generation_id']));rid=str(uuid.UUID(prov['request_id']))
 assert generated==(origin==p['generation'])
 if origin not in reports:
  report_path=source/'region-reread-queue-v1'/origin/f'page-{page:04}-{rid}.json'
  if not report_path.exists():report_path=source/'region-reread-queue-v1'/origin/f'page-{page:04}.json'
  raw=report_path.read_bytes()
  assert digest(raw)==prov['artifact_sha256'];report=json.loads(raw);request=report['request'];result=report['result']
  assert request['generation_id']==origin and request['request_id']==rid and request['source_sha256']==e['source_sha256']
  assert request['pdf_page']==page and request['render_sha256']==e['ocr_render_sha256']
  unsigned={k:v for k,v in request.items() if k!='request_sha256'}
  assert digest(json.dumps(unsigned,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())==request['request_sha256']
  policy={k:request[k] for k in ('method','code_sha256','languages','models','engine','psm','deadline_seconds')}
  if 'attempt_token' in request:
   assert type(request['attempt_token']) is int and request['attempt_token']>=1
   policy['attempt_token']=request['attempt_token']
  policy_hash=digest(json.dumps(policy,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode())
  assert str(uuid.uuid5(uuid.UUID(origin),str(page)+':'+policy_hash))==rid
  for field in ('request_sha256','request_id','render_sha256','code_sha256','engine','models'):
   assert prov[field]==request[field] and result[field]==request[field]
  assert result['status']=='COMPLETED' and len(result['regions'])==len(request['regions'])
  reports[origin]=report
 report=reports[origin];matches=[(i,r) for i,r in enumerate(report['result']['regions']) if r['source_span_id']==measurement['source_span_id']]
 assert len(matches)==1;index,stored=matches[0];assert stored==measurement
 wanted=report['request']['regions'][index];assert wanted['region_key']==stored['source_span_id']
 assert wanted['bbox']==stored['bbox']==d['bbox']
 if generated:assert stored['source_span_id']==row['id']
 directory=source/'region-reread-queue-v1'/origin/f'page-{page:04}'/rid/str(index)
 assert digest((directory/'crop.png').read_bytes())==stored['crop_sha256']
 assert [r['psm'] for r in stored['readings']]==[7,13]
 for reading in stored['readings']:
  raw=(directory/f"psm{reading['psm']}.tsv").read_bytes();assert digest(raw)==reading['tsv_sha256']
  words=[r for r in csv.DictReader(io.StringIO(raw.decode()),delimiter='\t',quoting=csv.QUOTE_NONE) if r['level']=='5' and r['text'].strip()]
  assert ' '.join(r['text'] for r in words)==reading['text']
  assert [float(r['conf']) for r in words]==reading['word_confidences']
 checked+=1
print(json.dumps({'source_artifacts_verified':True,'queue_measurements_verified':checked}))
'''
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',program],
        input=json.dumps({'spans':spans,'evidence':evidence,'generation':generation}),text=True))
