#!/usr/bin/env python3
"""Actual uploaded PDF, HTTP result, independent PostgreSQL and Poppler comparison."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

root=Path(__file__).resolve().parents[1];os.chdir(root)
base=os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/')
run=json.loads((root/'evidence/upload-ui/verification.json').read_text())
upload=run['upload_id'];token=(root/'secrets/api_token').read_text().strip()
checks=[]


def api(method,path,body=None,expected=200,auth=True,key=None):
    headers={'Authorization':'Bearer '+token} if auth else {}
    if key:headers['Idempotency-Key']=key
    if isinstance(body,dict):body=json.dumps(body).encode();headers['Content-Type']='application/json'
    try:
        with urllib.request.urlopen(urllib.request.Request(base+path,data=body,headers=headers,method=method),timeout=120) as response:
            code=response.status;result=response.read()
    except urllib.error.HTTPError as exc:code=exc.code;result=exc.read()
    assert code==expected,(path,code,result[:200])
    return json.loads(result)


status=api('GET','/v1/uploads/'+upload)
api('GET','/v1/uploads/'+upload,auth=False,expected=401)
api('GET','/v1/uploads',auth=False,expected=401)
sql="""SELECT json_build_object('status',u.status,'version',u.content_version_id,'sha',cv.sha256,
 'manifest',s.manifest,'source_count',(SELECT count(*) FROM editor.source_probes),
 'versions',(SELECT count(*) FROM editor.content_versions),'generations',(SELECT count(*) FROM editor.generations))
 FROM editor.uploads u JOIN editor.content_versions cv ON cv.id=u.content_version_id
 JOIN editor.source_probes s ON s.sha256=cv.sha256 WHERE u.id='%s'"""%upload
db=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',sql],text=True))
assert db['status']==status['status']=='COMPLETED' and db['version']==status['content_version_id']
assert db['sha']==run['source_sha256'] and db['source_count']==db['versions']==1 and db['generations']==0
manifest=api('GET','/v1/source-probes/'+db['sha'])
assert manifest==db['manifest']
info=subprocess.check_output(['docker','compose','exec','-T','parser','pdfinfo','/data/artifacts/'+db['sha']+'/original.pdf'],text=True)
pages=int(re.search(r'^Pages:\s+(\d+)',info,re.M).group(1))
assert pages==manifest['pdf_pages']==len(manifest['pages'])==run['pages']
source=Path(os.environ['EDITOR_VERIFY_PDF']).read_bytes()
assert hashlib.sha256(source).hexdigest()==db['sha'] and len(source)==manifest['bytes']
# Completed source attachment remains idempotent and does not create another version.
key='real-upload-acceptance:'+upload
first=api('POST','/v1/uploads/'+upload+'/complete',{'confirm':True},201,key=key)
second=api('POST','/v1/uploads/'+upload+'/complete',{'confirm':True},201,key=key)
assert first==second and first['id']==status['content_version_id']
report={'api':base,'database':'actual isolated Editor PostgreSQL','source_sha256':db['sha'],
 'pages':pages,'upload_id':upload,'http_pg_manifest_equal':True,'independent_pdfinfo_pages_equal':True,
 'original_bytes_equal':True,'completed_idempotency':True,'unauthorized_reads':401,
 'semantic_acceptance':False}
(root/'evidence/upload-api-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
