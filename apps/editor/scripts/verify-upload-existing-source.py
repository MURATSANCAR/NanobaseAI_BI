#!/usr/bin/env python3
"""Exercise deployed upload queue with the unchanged original book, not a fixture."""
import hashlib,json,os,subprocess,time,urllib.request,urllib.error
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/'evidence/source-spans-run.json').read_text())
base='http://127.0.0.1:8810';headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
original=(root/'runtime/input/reference.pdf').read_bytes();digest=hashlib.sha256(original).hexdigest()


def sql(query):
    return subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True).strip()


def api(method,path,body=None,key=None):
    h=dict(headers)
    if key:h['Idempotency-Key']='upload-queue-v2:'+key
    if isinstance(body,dict):body=json.dumps(body).encode();h['Content-Type']='application/json'
    with urllib.request.urlopen(urllib.request.Request(base+path,data=body,headers=h,method=method),timeout=120) as response:
        return response.status,json.load(response)


row=json.loads(sql("SELECT json_build_object('edition',cv.edition_id,'version',cv.id,'sha',cv.sha256) FROM editor.generations g JOIN editor.content_versions cv ON cv.id=g.content_version_id WHERE g.id='"+run['generation_id']+"'"))
assert row['sha']==digest
reference_sql="SELECT md5(string_agg(id::text||data::text,'' ORDER BY id)) FROM editor.records WHERE generation_id='"+run['generation_id']+"'"
before=sql(reference_sql)
_,upload=api('POST','/v1/editions/'+row['edition']+'/uploads',{'expected_bytes':len(original),'expected_sha256':digest},'session')
api('PUT',upload['upload_url'],original)
code,queued=api('POST','/v1/uploads/'+upload['id']+'/complete',{'confirm':True},'complete')
assert code==202 and queued['job_id']==upload['id']
for _ in range(90):
    _,status=api('GET','/v1/uploads/'+upload['id'])
    if status['status']=='COMPLETED':break
    assert status['status']=='PARSING',status
    time.sleep(2)
else:raise RuntimeError('UPLOAD_DID_NOT_COMPLETE')
assert status['content_version_id']==row['version']
assert sql(reference_sql)==before
result=json.loads(subprocess.check_output(['docker','compose','exec','-T','parser','cat','/data/artifacts/parse-queue/'+upload['id']+'.result.json']))
assert result['status']=='COMPLETED' and result['sha256']==digest and result['reused_artifacts']
report={'api':base,'generation_id':run['generation_id'],'upload_id':upload['id'],'source_sha256':digest,
        'original_version_reused':True,'analysis_records_unchanged':True,'parser_result':result,'semantic_acceptance':False}
(root/'evidence/upload-existing-source-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
