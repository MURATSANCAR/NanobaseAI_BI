#!/usr/bin/env python3
"""Real-book admission/cancel/restart acceptance in a separate installation only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1];os.chdir(root)
config=json.loads(subprocess.check_output(['docker','compose','config','--format','json']))
assert 'qualification' in config['name'],'Use an isolated qualification installation'
base=os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/')
pdf=Path(os.environ['EDITOR_VERIFY_PDF']).read_bytes();sha=hashlib.sha256(pdf).hexdigest()
run=json.loads((root/'evidence/upload-ui/verification.json').read_text())
assert sha==run['source_sha256']
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
key='real-upload-recovery:'+str(uuid.uuid4())


def api(method,path,body=None,status=200,operation=''):
    h=dict(headers)
    if operation:h['Idempotency-Key']=key+':'+operation
    if isinstance(body,dict):body=json.dumps(body).encode();h['Content-Type']='application/json'
    try:
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body,headers=h,method=method),timeout=60) as r:code=r.status;data=r.read()
    except urllib.error.HTTPError as e:code=e.code;data=e.read()
    assert code==status,(path,code,data[:200])
    return json.loads(data)


def sql(query):
    return subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True).strip()


def wait(upload,expected):
    for _ in range(90):
        status=api('GET','/v1/uploads/'+upload)['status']
        if status==expected:return
        assert status not in ('FAILED','COMPLETED','CANCELLED'),(status,expected)
        time.sleep(2)
    raise RuntimeError('UPLOAD_RECOVERY_TIMEOUT')


edition=sql("SELECT edition_id FROM editor.uploads WHERE id='"+run['upload_id']+"'")
before=sql("SELECT md5(manifest::text) FROM editor.source_probes WHERE sha256='"+sha+"'")
uploads=[]
for n in range(4):
    u=api('POST','/v1/editions/'+edition+'/uploads',{'expected_bytes':len(pdf),'expected_sha256':sha},201,'session-'+str(n))
    api('PUT',u['upload_url'],pdf)
    uploads.append(u['id'])
parser=subprocess.check_output(['docker','compose','ps','-q','parser'],text=True).strip()
assert parser
subprocess.run(['docker','pause',parser],check=True,stdout=subprocess.DEVNULL)
try:
    for n in range(2):
        result=api('POST','/v1/uploads/'+uploads[n]+'/complete',{'confirm':True},202,'complete-'+str(n))
        assert result['job_id']==uploads[n]
    rejected=api('POST','/v1/uploads/'+uploads[2]+'/complete',{'confirm':True},429,'complete-2')
    assert rejected['detail']=='SOURCE_PARSE_CAPACITY_FULL'
    sealed=api('PUT','/v1/uploads/'+uploads[0]+'/content',pdf,409)
    assert sealed['detail']=='UPLOAD_SEALED'
    api('POST','/v1/jobs/'+uploads[0]+'/cancel',{'purpose':'validation'},200,'cancel-0')
finally:
    subprocess.run(['docker','unpause',parser],check=True,stdout=subprocess.DEVNULL)
wait(uploads[0],'CANCELLED');wait(uploads[1],'COMPLETED')
api('POST','/v1/uploads/'+uploads[2]+'/complete',{'confirm':True},202,'complete-2')
wait(uploads[2],'COMPLETED')
subprocess.run(['docker','compose','stop','parser'],check=True)
try:
    queued=api('POST','/v1/uploads/'+uploads[3]+'/complete',{'confirm':True},202,'complete-3')
    assert queued['job_id']==uploads[3]
finally:
    subprocess.run(['docker','compose','start','parser'],check=True)
wait(uploads[3],'COMPLETED')
assert api('GET','/v1/jobs/'+uploads[3])['task']=='source_parse'
after=sql("SELECT md5(manifest::text) FROM editor.source_probes WHERE sha256='"+sha+"'")
assert before==after
assert sql('SELECT count(*) FROM editor.content_versions')=='1'
assert sql('SELECT count(*) FROM editor.reviews')=='0'
report={'api':base,'source_sha256':sha,'uploads':uploads,'capacity_limit':2,'excess_rejected':429,
        'sealed_upload_rejected':409,'cancellation':'PASS','queue_survives_parser_restart':'PASS',
        'source_manifest_unchanged':True,'content_versions':1,'editorial_decisions_written':0}
(root/'evidence/upload-recovery-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
