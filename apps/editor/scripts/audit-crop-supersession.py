#!/usr/bin/env python3
"""Read-only measurement of full-page veto versus immutable crop/PDF agreement."""
import argparse,hashlib,json,os,re,statistics,subprocess,unicodedata,urllib.request,uuid
from collections import Counter
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--generation',required=True,type=uuid.UUID);a=p.parse_args()
root=Path(__file__).resolve().parents[1];os.chdir(root);gen=str(a.generation);token=(root/'secrets/api_token').read_text().strip()
def sql(q):return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',q],text=True))
def db():return sql("SELECT json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key) FROM editor.records WHERE generation_id='"+gen+"' AND kind='source_spans'")
def words(s):return re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',s or '').replace('İ','i').replace('I','ı').lower())
def clean(s):return not any(unicodedata.category(c) in ('Co','Cs') or c=='\ufffd' for c in s or '')
rows=db();api=[]
while True:
 with urllib.request.urlopen(urllib.request.Request(a.base+f'/v1/generations/{gen}/source_spans?offset={len(api)}&limit=100',headers={'Authorization':'Bearer '+token}),timeout=60) as r:b=json.load(r)
 api.extend(b['items'])
 if not b['has_more']:break
assert api==rows
selected=[];counts=Counter()
for row in rows:
 d=row['data']
 if d['status']!='NEEDS_REVIEW':continue
 counts['review']+=1;rr=d.get('reread_measurement');region=words(d['region_text'])
 if not rr or not region or not clean(d['region_text']) or not d['pdf_usable'] or not clean(d['pdf_text']):continue
 readings=rr['readings'];assert [r['psm'] for r in readings]==[7,13]
 if not all(clean(r['text']) and words(r['text'])==region for r in readings) or words(d['pdf_text'])!=region:continue
 if not words(d['secondary_text']) or words(d['secondary_text'])==region:continue
 counts['crop_and_pdf_agree_fullpage_tess_conflicts']+=1
 if (d['region_score'] or 0)<.9:counts['excluded_low_region_score']+=1;continue
 counts['high_region_score']+=1;counts['role_'+d['role']]+=1
 literal=all(r['text']==d['region_text']==d['pdf_text'] for r in readings);counts['literal_all_equal']+=literal
 full=[w['confidence'] for w in d['secondary_word_regions'] if w.get('confidence',-1)>=0]
 entry={'id':row['id'],'record_key':row['record_key'],'data':d,'literal_all_equal':literal,
  'confidence_summary':{'full_page_mean':statistics.mean(full) if full else None,'full_page_min':min(full) if full else None,
  'crops':[{'psm':r['psm'],'mean':statistics.mean(r['word_confidences']) if r['word_confidences'] else None,'min':min(r['word_confidences']) if r['word_confidences'] else None} for r in readings]}}
 selected.append(entry)
source=sql("SELECT to_json(cv.sha256) FROM editor.generations g JOIN editor.content_versions cv ON cv.id=g.content_version_id WHERE g.id='"+gen+"'")
runner=r'''
import hashlib,io,json,math,sys
from pathlib import Path
from PIL import Image,ImageOps
p=json.load(sys.stdin);checks=[]
def h(raw):return hashlib.sha256(raw).hexdigest()
for row in p['rows']:
 d=row['data'];rr=d['reread_measurement'];prov=d['reread_provenance'];base=Path('/data/artifacts')/p['sha'];n=d['pdf_page']
 raw=(base/'region-reread-v1'/prov['generation_id']/f'page-{n:04}.json').read_bytes();assert h(raw)==prov['artifact_sha256'];artifact=json.loads(raw)
 assert [r for r in artifact['regions'] if r['source_span_id']==rr['source_span_id']]==[rr]
 assert rr['bbox']==d['bbox'];render=(base/'ocr-regions-v2'/f'page-{n:04}.png').read_bytes();assert h(render)==d['render_sha256']==artifact['render_sha256']
 im=Image.open(io.BytesIO(render)).convert('RGB');x,y,w,hh=d['bbox'];bounds=[math.floor(x*im.width),math.floor(y*im.height),min(im.width,math.ceil((x+w)*im.width)),min(im.height,math.ceil((y+hh)*im.height))]
 assert bounds==rr['crop_pixels'];crop=im.crop(bounds);scale=min(3,max(1,64/crop.height));crop=crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))))
 crop=ImageOps.expand(crop,border=16,fill='white');s=io.BytesIO();crop.save(s,format='PNG');assert h(s.getvalue())==rr['crop_sha256']
 checks.append({'id':row['id'],'original_reread_artifact_hash_equal':True,'record_measurement_equal':True,'bbox_equal':True,'render_hash_equal':True,'recreated_crop_hash_equal':True})
print(json.dumps(checks))
'''
checks=json.loads(subprocess.check_output(['docker','compose','exec','-T','parser','python','-c',runner],input=json.dumps({'sha':source,'rows':selected}),text=True));assert rows==db()
result={'generation_id':gen,'api':a.base,'counts':dict(counts),'api_pg_equal':True,'source_records_unchanged':True,'model_calls':0,'source_or_review_writes':0,
 'semantic_acceptance':False,'source_records_sha256':hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=True).encode()).hexdigest(),
 'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'provenance_checks':checks,'candidates':selected}
out=root/'evidence'/('crop-supersession-audit-'+gen+'.json');out.write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k not in ('candidates','provenance_checks')}|{'evidence':str(out),'keys':[r['record_key'] for r in selected]},indent=2))
