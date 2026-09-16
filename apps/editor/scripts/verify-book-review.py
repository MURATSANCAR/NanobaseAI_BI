#!/usr/bin/env python3
"""Actual pending review and stale-write rejection; never simulates human approval."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.error

root=Path(__file__).resolve().parents[1]; os.chdir(root)
run=json.loads((root/'evidence/reference-book-run.json').read_text()); gen=run['job']['generation_id']
token=(root/'secrets/api_token').read_text().strip(); base='http://127.0.0.1:8810'


def call(path,body=None,key=None,expected=200):
    headers={'Authorization':'Bearer '+token}
    if body is not None: headers['Content-Type']='application/json'
    if key: headers['Idempotency-Key']=key
    try:
        response=urllib.request.urlopen(urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=30)
        code=response.status; data=response.read()
    except urllib.error.HTTPError as exc: code=exc.code; data=exc.read()
    assert code==expected,(path,code)
    return json.loads(data)


visual=call('/v1/generations/'+gen+'/visuals?limit=1')['items'][0]
before=hashlib.sha256(json.dumps(visual['data'],sort_keys=True).encode()).hexdigest()
body={'target_id':visual['id'],'expected_version':0,'decision':'NEEDS_REVIEW',
      'reason':'Kaynak sayfa görseli ile modelin logo ayrıntısı açıklaması karşılaştırılmalı. Otomatik kalite incelemesi; insan editör onayı değildir.'}
key='real-review-v1-'+gen
created=call('/v1/reviews',body,key,201)
assert call('/v1/reviews',body,key,201)==created
call('/v1/reviews',body,key+'-stale',409)
after=call('/v1/generations/'+gen+'/visuals?limit=1')['items'][0]
assert before==hashlib.sha256(json.dumps(after['data'],sort_keys=True).encode()).hexdigest()
query="SELECT json_build_object('decision',decision,'version',version,'target_id',target_id) FROM editor.reviews WHERE id='"+created['id']+"'"
reference=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))
assert reference=={'decision':'NEEDS_REVIEW','version':1,'target_id':visual['id']}
result={'generation_id':gen,'review_id':created['id'],'real_api_equals_independent_db':True,
  'idempotency_verified':True,'stale_write_status':409,'model_record_preserved':True,'human_accepted':False}
(root/'evidence/book-review-verified.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
