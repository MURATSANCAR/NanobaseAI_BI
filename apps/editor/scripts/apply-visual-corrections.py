#!/usr/bin/env python3
"""Apply reviewed observations from the actual PDF through the operator API.

Run only in the connected installation. Input is source-review work, not a
synthetic fixture or model answer key. It never grants human editorial approval.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import urllib.error

root=Path(__file__).resolve().parents[1]; os.chdir(root)
observations=json.loads(Path(sys.argv[1]).read_text())
run=json.loads((root/'evidence/reference-book-run.json').read_text()); gen=run['job']['generation_id']
token=(root/'secrets/api_token').read_text().strip()


def call(path,body=None,key=None,expected=200):
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
    if key: headers['Idempotency-Key']=key
    req=urllib.request.Request('http://127.0.0.1:8810'+path,
        data=json.dumps(body).encode() if body is not None else None,headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=30) as response: code=response.status; data=response.read()
    except urllib.error.HTTPError as exc: code=exc.code; data=exc.read()
    assert code==expected,(path,code,data.decode()[:300])
    return json.loads(data)


visuals=call('/v1/generations/'+gen+'/visuals?limit=100')['items']
original_hash=hashlib.sha256(json.dumps(visuals,sort_keys=True).encode()).hexdigest()
by_page={r['data']['pdf_page']:r for r in visuals}
states={}; offset=0
while True:
    page=call(f'/v1/reviews?generation_id={gen}&limit=100&offset={offset}')['items']
    states.update({r['id']:r for r in page})
    if len(page)<100: break
    offset+=len(page)
prior=call('/v1/generations/'+gen+'/visual_corrections?limit=100')['items']
applied=[]
for observation in observations:
    visual=by_page[observation['pdf_page']]
    existing=next((r for r in prior if r['data']['target_id']==visual['id'] and
        r['data']['description']==observation['description'] and r['data']['reason']==observation['reason']),None)
    if existing:
        applied.append(existing['id']); continue
    body={'target_id':visual['id'],'expected_version':states[visual['id']]['review_version'],
          'description':observation['description'],'reason':observation['reason'],
          'provenance':'codex_assisted_source_observation'}
    fingerprint=hashlib.sha256(json.dumps(observation,sort_keys=True).encode()).hexdigest()[:20]
    key='source-observation-'+gen+'-'+fingerprint
    if '--check-running-guard' in sys.argv:
        result=call('/v1/visual-corrections',body,key,409)
        assert result['detail']=='PAUSE_ANALYSIS_BEFORE_SOURCE_CORRECTION',result
        print(json.dumps({'running_mutation_rejected':True,'status':409}));sys.exit(0)
    result=call('/v1/visual-corrections',body,key,201)
    assert call('/v1/visual-corrections',body,key,201)==result
    stale=call('/v1/visual-corrections',body,key+'-stale',409)
    assert stale['detail']=='REVIEW_VERSION_CONFLICT',stale
    applied.append(result['id'])
    print(json.dumps({'pdf_page':observation['pdf_page'],'correction_id':result['id'],'human_accepted':False}),flush=True)

after=call('/v1/generations/'+gen+'/visuals?limit=100')['items']
assert hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest()==original_hash
actual=call('/v1/generations/'+gen+'/visual_corrections?limit=100')['items']
query="SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='"+gen+"' AND kind='visual_corrections'"
reference=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))
assert actual==reference
result={'generation_id':gen,'corrections':len(applied),'original_model_records_unchanged':True,
        'api_equals_independent_db':True,'idempotency_verified':True,'stale_version_rejected':True,
        'provenance':'codex_assisted_source_observation','human_accepted':False}
(root/'evidence/book-source-correction-verified.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
