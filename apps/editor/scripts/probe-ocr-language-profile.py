#!/usr/bin/env python3
"""Bounded real-region OCR language comparison; artifacts only, no source writes."""
import argparse,base64,hashlib,json,os,re,subprocess,unicodedata,urllib.request,uuid
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--generation',type=uuid.UUID,required=True)
p.add_argument('--all-page',type=int,required=True);p.add_argument('--sample-pages',type=int,nargs='+',required=True)
p.add_argument('--per-status',type=int,default=3);a=p.parse_args();assert 1<=a.per_status<=5
root=Path(__file__).resolve().parents[1];os.chdir(root);gen=str(a.generation)
token=(root/'secrets/api_token').read_text().strip()
def sql(q):return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',q],text=True))
def database():return sql("SELECT json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key) FROM editor.records WHERE generation_id='"+gen+"' AND kind='source_spans'")
def sha(v):return hashlib.sha256(v).hexdigest()
before=database();api=[]
while True:
 with urllib.request.urlopen(urllib.request.Request(a.base+f'/v1/generations/{gen}/source_spans?offset={len(api)}&limit=100',headers={'Authorization':'Bearer '+token}),timeout=60) as r:b=json.load(r)
 api.extend(b['items'])
 if not b['has_more']:break
assert api==before
source=sql("SELECT to_json(cv.sha256) FROM editor.generations g JOIN editor.content_versions cv ON cv.id=g.content_version_id WHERE g.id='"+gen+"'")
selected=[r for r in api if r['data']['pdf_page']==a.all_page]
for page in a.sample_pages:
 for status in ('NEEDS_REVIEW','TEXT_AGREED'):
  selected.extend([r for r in api if r['data']['pdf_page']==page and r['data']['status']==status][:a.per_status])
assert selected and len(selected)<=50 and len({r['id'] for r in selected})==len(selected)
runner=r'''
import base64,csv,hashlib,io,json,math,os,subprocess,sys,tempfile,time
from pathlib import Path
from PIL import Image,ImageOps
p=json.load(sys.stdin);out=[];started=time.monotonic()
def h(b):return hashlib.sha256(b).hexdigest()
for row in p['rows']:
 d=row['data'];raw=(Path('/data/artifacts')/p['sha']/'ocr-regions-v2'/f"page-{d['pdf_page']:04}.png").read_bytes()
 assert h(raw)==d['render_sha256'];im=Image.open(io.BytesIO(raw)).convert('RGB');x,y,w,hh=d['bbox']
 bounds=[math.floor(x*im.width),math.floor(y*im.height),min(im.width,math.ceil((x+w)*im.width)),min(im.height,math.ceil((y+hh)*im.height))]
 crop=im.crop(bounds);scale=min(3,max(1,64/crop.height));crop=crop.resize((max(1,round(crop.width*scale)),max(1,round(crop.height*scale))))
 crop=ImageOps.expand(crop,border=16,fill='white');s=io.BytesIO();crop.save(s,format='PNG');png=s.getvalue();readings=[]
 with tempfile.TemporaryDirectory() as tmp:
  path=Path(tmp)/'crop.png';path.write_bytes(png)
  for lang in ('tur+eng','tur'):
   for psm in (7,13):
    assert time.monotonic()-started<600
    begin=time.monotonic();proc=subprocess.run(['tesseract',str(path),'stdout','-l',lang,'--psm',str(psm),'tsv'],capture_output=True,check=True,timeout=20,env={**os.environ,'OMP_THREAD_LIMIT':'1'})
    words=[r for r in csv.DictReader(io.StringIO(proc.stdout.decode()),delimiter='\t',quoting=csv.QUOTE_NONE) if r['level']=='5' and r['text'].strip()]
    readings.append({'language':lang,'psm':psm,'text':' '.join(r['text'] for r in words),'word_confidences':[float(r['conf']) for r in words],
       'tsv_sha256':h(proc.stdout),'tsv_base64':base64.b64encode(proc.stdout).decode(),'stderr':proc.stderr.decode(),'seconds':round(time.monotonic()-begin,3)})
 out.append({'id':row['id'],'record_key':row['record_key'],'pdf_page':d['pdf_page'],'bbox':d['bbox'],'render_sha256':h(raw),'crop_pixels':bounds,
   'crop_sha256':h(png),'crop_base64':base64.b64encode(png).decode(),'readings':readings})
print(json.dumps({'regions':out,'seconds':round(time.monotonic()-started,3),'engine':subprocess.check_output(['tesseract','--version'],text=True).splitlines()[0],
 'models':{l:h((Path('/usr/share/tesseract-ocr/5/tessdata')/(l+'.traineddata')).read_bytes()) for l in ('tur','eng')}}))
'''
result=json.loads(subprocess.check_output(['docker','compose','exec','-T','parser','python','-c',runner],input=json.dumps({'sha':source,'rows':selected}),text=True,timeout=650))
assert before==database()
out=root/'evidence'/('ocr-language-profile-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
def words(s):return re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',s or '').replace('İ','i').replace('I','ı').lower())
counts=Counter();byid={r['id']:r['data'] for r in selected}
for r in result['regions']:
 d=byid[r['id']];folder=out/r['record_key'];folder.mkdir();png=base64.b64decode(r.pop('crop_base64'));assert sha(png)==r['crop_sha256'];(folder/'crop.png').write_bytes(png)
 r['original_status']=d['status'];r['original_readings']={k:d.get(k) for k in ('raw_text','region_text','secondary_text','pdf_text','pdf_usable','reread_measurement')}
 r['comparisons']={};counts['selected_'+d['status']]+=1
 for reading in r['readings']:
  raw=base64.b64decode(reading.pop('tsv_base64'));assert sha(raw)==reading['tsv_sha256'];(folder/(reading['language']+'-psm'+str(reading['psm'])+'.tsv')).write_bytes(raw)
 for language in ('tur+eng','tur'):
  readings=[x for x in r['readings'] if x['language']==language];left,right=[words(x['text']) for x in readings];stable=bool(left) and left==right
  cmp={'stable':stable,'matches_region':stable and left==words(d['region_text']),
   'matches_usable_pdf':stable and d['pdf_usable'] and left==words(d['pdf_text']),
   'matches_original':stable and left==words(d['raw_text'])}
  r['comparisons'][language]=cmp
  for k,v in cmp.items():counts[language+'_'+k]+=int(v)
  if d['status']=='TEXT_AGREED':counts[language+'_agreed_controls_matching_original']+=int(cmp['matches_original'])
 old,new=r['comparisons']['tur+eng'],r['comparisons']['tur']
 for target in ('matches_region','matches_usable_pdf','matches_original'):
  counts['tur_gained_'+target]+=int(new[target] and not old[target]);counts['tur_lost_'+target]+=int(old[target] and not new[target])
result.update(generation_id=gen,source_sha256=source,api=a.base,counts=dict(counts),source_records_unchanged=True,api_pg_equal=True,
 source_records_sha256=sha(json.dumps(before,sort_keys=True,ensure_ascii=True).encode()),verifier_sha256=sha(Path(__file__).read_bytes()),
 semantic_acceptance=False,source_or_review_writes=0,selection={'all_page':a.all_page,'sample_pages':a.sample_pages,'per_status':a.per_status})
(out/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='regions'}|{'evidence':str(out)},ensure_ascii=False,indent=2))
