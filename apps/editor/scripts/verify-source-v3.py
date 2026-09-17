#!/usr/bin/env python3
"""Replay the actual source API/PG/artifacts through the proposed v3 image."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request

root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/'evidence/source-spans-run.json').read_text());gen=run['generation_id']
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
rows=[];offset=0
while True:
    with urllib.request.urlopen(urllib.request.Request(
        f'http://127.0.0.1:8810/v1/generations/{gen}/source_spans?offset={offset}&limit=100',headers=headers),timeout=60) as response:
        data=json.load(response)
    rows+=data['items']
    if not data['has_more']:break
    offset+=len(data['items'])
code='''import json,sys
from collections import Counter
from editor.book_store import ROOT,source_for,get_records,sha
from editor.source_alignment import reader_text
from editor.source_pipeline import optical_verdict,reread_measurements,reusable_claim_candidates
gen=sys.argv[1];before=get_records(gen,'source_spans');root=ROOT/source_for(gen)['sha256']
fingerprint=sha(json.dumps(before,sort_keys=True,default=str).encode());summary=[];totals=Counter()
for evidence in get_records(gen,'evidence'):
 d=evidence['data'];page=d['pdf_page'];pdf=json.loads((root/'pdf-text-regions-v1'/f'page-{page:04}.json').read_text())
 rereads,_=reread_measurements(root,gen,evidence);old=[r for r in before if r['data']['pdf_page']==page];new=[]
 for row in old:
  s=row['data'];native,words,usable=reader_text(s['bbox'],pdf['lines']);secondary,_,_=reader_text(s['bbox'],d['blocks'])
  bad=any(0xE000<=ord(c)<=0xF8FF or 0xF0000<=ord(c)<=0xFFFFD or 0x100000<=ord(c)<=0x10FFFD for c in native)
  if bad:assert not usable;totals['private_unicode_rejected']+=1
  line={'text':s['raw_text'],'region_text':s['region_text'],'score':s['score'],'region_score':s['region_score']}
  verdict=optical_verdict(line,secondary,native,usable,rereads.get(str(row['id'])))
  new.append({**row,'data':{**s,'status':verdict['status'],'issues':verdict['issues']}})
  totals['old_agreed']+=s['status']=='TEXT_AGREED';totals['new_agreed']+=verdict['status']=='TEXT_AGREED'
  totals['rereads_consumed']+=str(row['id']) in rereads
  totals['reread_conflicts']+=verdict['reread_state']=='DISAGREES'
  totals['changed_status']+=verdict['status']!=s['status']
 reuse=reusable_claim_candidates(gen,evidence['record_key'],new)
 summary.append({'page':page,'spans':len(old),'old_agreed':sum(r['data']['status']=='TEXT_AGREED' for r in old),
  'new_agreed':sum(r['data']['status']=='TEXT_AGREED' for r in new),'unchanged_model_context':reuse is not None})
assert fingerprint==sha(json.dumps(get_records(gen,'source_spans'),sort_keys=True,default=str).encode())
print(json.dumps({'source_records':before,'generation_id':gen,'totals':dict(totals),'pages':summary,'original_records_unchanged':True,'semantic_acceptance':False},default=str))
'''
result=json.loads(subprocess.check_output(['docker','compose','run','--rm','--no-deps','-T','--entrypoint','python','api','-c',code,gen],text=True))
assert result.pop('source_records')==rows,'API_PG_SOURCE_MISMATCH'
result['api_pg_source_equal']=True
output=os.environ.get('EDITOR_REPLAY_OUTPUT','source-v3-replay.json')
assert Path(output).name==output and output.endswith('.json'),'INVALID_OUTPUT_NAME'
(root/'evidence'/output).write_text(json.dumps(result,indent=2))
print(json.dumps(result),flush=True)
