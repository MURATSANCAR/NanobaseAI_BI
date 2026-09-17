#!/usr/bin/env python3
"""Read-only real-artifact measurement of line flags versus selected-word Unicode."""
import argparse,hashlib,json,os,subprocess,urllib.request,uuid
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--generation',required=True,type=uuid.UUID);a=p.parse_args()
root=Path(__file__).resolve().parents[1];os.chdir(root);gen=str(a.generation)
token=(root/'secrets/api_token').read_text().strip()
def sql(q):return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',q],text=True))
def db():return sql("SELECT json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key) FROM editor.records WHERE generation_id='"+gen+"' AND kind='source_spans'")
rows=db();api=[]
while True:
 with urllib.request.urlopen(urllib.request.Request(a.base+f'/v1/generations/{gen}/source_spans?offset={len(api)}&limit=100',headers={'Authorization':'Bearer '+token}),timeout=60) as r:b=json.load(r)
 api.extend(b['items'])
 if not b['has_more']:break
assert rows==api
source=sql("SELECT to_json(cv.sha256) FROM editor.generations g JOIN editor.content_versions cv ON cv.id=g.content_version_id WHERE g.id='"+gen+"'")
runner=r'''
import hashlib,json,math,sys,unicodedata
from pathlib import Path
from collections import Counter
p=json.load(sys.stdin);counts=Counter();affected=[];pages={};rawcounts=Counter()
def bad(s):return any(unicodedata.category(c) in ('Co','Cs') or c=='\ufffd' for c in s)
def valid(b):return isinstance(b,list) and len(b)==4 and all(isinstance(v,(int,float)) and math.isfinite(v) for v in b) and min(b)>=0 and b[2]>0 and b[3]>0 and b[0]+b[2]<=1.001 and b[1]+b[3]<=1.001
for row in p['rows']:
 d=row['data'];n=d['pdf_page'];counts['source_spans']+=1
 if n not in pages:
  path=Path('/data/artifacts')/p['sha']/'pdf-text-regions-v1'/f'page-{n:04}.json';raw=path.read_bytes();artifact=json.loads(raw)
  assert artifact['source_sha256']==p['sha'] and artifact['pdf_page']==n
  pages[n]=(artifact,hashlib.sha256(raw).hexdigest())
  for line in artifact['lines']:
   rawcounts['lines']+=1;rawcounts['flagged_lines']+=bool(line.get('corrupt_private_unicode'))
   rawcounts['flag_matches_any_bad_word']+=bool(line.get('corrupt_private_unicode'))==any(bad(w['text']) for w in line['words'])
   if line.get('corrupt_private_unicode'):
    rawcounts['clean_words_in_flagged_lines']+=sum(not bad(w['text']) for w in line['words'])
 artifact,digest=pages[n];assert digest==d['pdf_artifact_sha256'];x,y,w,h=d['bbox'];selected=[];clean_selected=[];outside=[]
 for li,line in enumerate(artifact['lines']):
  selected_indices=[]
  for wi,word in enumerate(line['words']):
   b=word['bbox']
   if not valid(b):continue
   wx,wy,ww,wh=b
   ox=max(0,min(x+w,wx+ww)-max(x,wx))/ww;oy=max(0,min(y+h,wy+wh)-max(y,wy))/min(h,wh)
   if x-.002<=wx+ww/2<=x+w+.002 and y-.004<=wy+wh/2<=y+h+.004 and ox>=.5 and oy>=.5:
    selected_indices.append(wi);selected.append({**word,'line_index':li,'word_index':wi,'corrupt_private_unicode':line.get('corrupt_private_unicode',False) or bad(word['text'])})
    clean_selected.append(not bad(word['text']))
  if selected_indices and line.get('corrupt_private_unicode'):
   outside.extend({'line_index':li,'word_index':wi,'text':word['text'],'bbox':word['bbox']} for wi,word in enumerate(line['words']) if wi not in selected_indices and bad(word['text']))
 assert selected==d['pdf_word_regions'];assert ' '.join(s['text'] for s in selected)==d['pdf_text']
 old=bool(selected) and not any(s['corrupt_private_unicode'] for s in selected);new=bool(selected) and all(clean_selected)
 assert old==d['pdf_usable'];counts['old_usable']+=old;counts['word_local_usable']+=new
 if not old and new:
  counts['false_unusable_'+d['status']]+=1
  affected.append({'id':row['id'],'record_key':row['record_key'],'pdf_page':n,'bbox':d['bbox'],'status':d['status'],'selected_pdf_text':d['pdf_text'],
   'selected_words':selected,'unselected_corrupt_words':outside,'region_text':d['region_text'],'raw_text':d['raw_text'],'secondary_text':d['secondary_text']})
 counts['selected_contains_actual_corruption']+=bool(selected) and not all(clean_selected)
print(json.dumps({'counts':dict(counts),'raw_artifact_counts':dict(rawcounts),'affected':affected,'artifact_pages':len(pages)}))
'''
result=json.loads(subprocess.check_output(['docker','compose','exec','-T','parser','python','-c',runner],input=json.dumps({'sha':source,'rows':rows}),text=True))
assert rows==db()
result.update(generation_id=gen,api=a.base,source_sha256=source,at=datetime.now(timezone.utc).isoformat(),api_pg_equal=True,source_records_unchanged=True,
 source_records_sha256=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=True).encode()).hexdigest(),verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 source_or_review_writes=0,model_calls=0,semantic_acceptance=False)
out=root/'evidence'/('pdf-corruption-scope-'+gen+'.json');out.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result|{'evidence':str(out)},ensure_ascii=False,indent=2))
