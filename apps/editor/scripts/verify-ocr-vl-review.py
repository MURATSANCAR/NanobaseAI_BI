#!/usr/bin/env python3
"""Real API/PG/artifact check for inherited OCR candidates; never edits book records."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request

root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/'evidence/source-spans-run.json').read_text())
gen=run['generation_id']
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
url=f'http://127.0.0.1:8810/v1/generations/{gen}/source-review'
with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as response:
    report=json.load(response)
code='''import json,sys
from pathlib import Path
from collections import Counter
from editor.book_store import get_records,source_for,ROOT,sha
report=json.load(sys.stdin);gen=report['generation_id'];source=source_for(gen)
before=get_records(gen,'source_spans');fingerprint=sha(json.dumps(before,sort_keys=True,default=str).encode())
rows={str(r['id']):r for r in before};counts=Counter();checked=[]
for page in report['pages']:
 for region in page['regions']:
  candidate=region.get('ocr_vl')
  if candidate is None:continue
  row=rows[region['span_id']];d=row['data'];origin=candidate['source_generation_id'];span=candidate['measured_source_span_id']
  assert ((origin==gen and span==str(row['id']))
    or (origin==d['reused_from_generation'] and span==d['reused_source_span_id'])
    or (origin==(d.get('reread_provenance') or {}).get('generation_id') and span==(d.get('reread_measurement') or {}).get('source_span_id')))
  path=ROOT/source['sha256']/'ocr-vl-regions-v2'/origin/(span+'.json')
  raw=path.read_bytes();artifact=json.loads(raw)
  assert sha(raw)==candidate['artifact_sha256']
  assert artifact['source_sha256']==source['sha256'] and artifact['render_sha256']==d['render_sha256']
  assert artifact['bbox']==d['bbox'] and artifact['pdf_page']==page['pdf_page']
  for key in ('text','complete','status','code_sha256','crop_sha256','seconds'):
   assert artifact[key]==candidate[key],key
  assert not candidate['eligible_for_synthesis'] and d['status']=='NEEDS_REVIEW'
  counts['regions']+=1;counts['complete']+=candidate['complete'];counts[candidate['reading_class']]+=1
  checked.append({'span_id':region['span_id'],'pdf_page':page['pdf_page'],'artifact_sha256':sha(raw)})
assert counts['regions']>0,'NO_OCR_VL_RESULTS'
assert fingerprint==sha(json.dumps(get_records(gen,'source_spans'),sort_keys=True,default=str).encode())
print(json.dumps({'generation_id':gen,'counts':dict(counts),'checks':checked,'source_records_unchanged':True,'semantic_acceptance':False}))
'''
result=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],
    input=json.dumps(report),text=True))
(root/'evidence/ocr-vl-review-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='checks'}),flush=True)
