#!/usr/bin/env python3
"""Real deployed API, real PDF and independent PostgreSQL comparison. Run on server."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.error

root=Path(__file__).resolve().parents[1]; os.chdir(root)
run=json.loads((root/'evidence/reference-book-run.json').read_text())
token=(root/'secrets/api_token').read_text().strip(); base='http://127.0.0.1:8810'
checks=[]


def call(method,path,body=None,key=None,authenticated=True,expected=200):
    headers={}
    if authenticated: headers['Authorization']='Bearer '+token
    if key: headers['Idempotency-Key']='real-book-verification-'+key
    if isinstance(body,dict): body=json.dumps(body).encode(); headers['Content-Type']='application/json'
    request=urllib.request.Request(base+path,data=body,headers=headers,method=method)
    try:
        response=urllib.request.urlopen(request,timeout=120); code=response.status; data=response.read()
    except urllib.error.HTTPError as exc: code=exc.code; data=exc.read()
    assert code==expected,(path,code,data[:200])
    return json.loads(data)


gen=run['job']['generation_id']; job=run['job']['job_id']; edition=run['edition']['id']
original=(root/'runtime/input/reference.pdf').read_bytes()
upload_body={'expected_bytes':len(original),'expected_sha256':hashlib.sha256(original).hexdigest()}
upload=call('POST','/v1/editions/'+edition+'/uploads',upload_body,'upload',expected=201)
same=call('POST','/v1/editions/'+edition+'/uploads',upload_body,'upload',expected=201)
assert upload==same; checks.append('upload_idempotency')
if not (root/'evidence/real-upload-completed.json').exists():
    call('POST','/v1/uploads/'+upload['id']+'/complete',{'confirm':True},'complete',expected=409)
    checks.append('incomplete_upload_rejected')
call('PUT',upload['upload_url'],original)
complete=call('POST','/v1/uploads/'+upload['id']+'/complete',{'confirm':True},'complete',expected=201)
assert complete['id']==run['source']['id']
(root/'evidence/real-upload-completed.json').write_text(json.dumps(complete,indent=2))
checks.append('real_pdf_upload_hash_and_content_version')
records=call('GET','/v1/generations/'+gen+'/evidence?limit=100')
query="SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='"+gen+"' AND kind='evidence'"
independent=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))
assert records['items']==independent
assert records['total']==len(independent)==48 and not records['has_more']
checks.append('full_api_evidence_equals_independent_postgresql_48_pages')
first=records['items'][0]
call('GET','/v1/evidence/'+first['id'],authenticated=False,expected=401)
call('GET','/v1/visuals/'+first['id'],authenticated=False,expected=401)
checks.append('real_evidence_and_visual_unauthenticated_401')
call('POST','/v1/generations/'+gen+'/activate',{'purpose':'validation'},'activate',expected=409)
checks.append('incomplete_generation_activation_rejected')
state=call('GET','/v1/jobs/'+job)
report={'environment':'nanobase-direct remote Linux Docker','api':base,'database':'editor PostgreSQL',
        'source_sha256':complete['sha256'],'generation_id':gen,'checks':checks,'job_status':state['status'],
        'semantic_acceptance':'PENDING','human_editor_acceptance':False}
(root/'evidence/book-api-verified.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
