#!/usr/bin/env python3
"""Reject invalid priority requests against an existing real book, without jobs."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
import uuid

p=argparse.ArgumentParser()
p.add_argument('--base',required=True)
p.add_argument('--content-version',required=True,type=uuid.UUID)
a=p.parse_args()
root=Path(__file__).resolve().parents[1];os.chdir(root)
token=(root/'secrets/api_token').read_text().strip()

def sql(q):
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres',
        'psql','-U','postgres','-d','editor','-Atc',q],text=True))

def counts():
    return sql("SELECT json_build_object('jobs',(SELECT count(*) FROM editor.jobs),'generations',(SELECT count(*) FROM editor.generations))")

source=sql("SELECT json_build_object('sha',cv.sha256,'manifest',s.manifest) FROM editor.content_versions cv JOIN editor.source_probes s ON s.sha256=cv.sha256 WHERE cv.id='"+str(a.content_version)+"'")
pages=source['manifest']['pdf_pages'];existing=source['manifest']['pages'][0]['pdf_page']
assert pages>=1 and 1<=existing<=pages
report={'api':a.base,'content_version_id':str(a.content_version),'source_sha256':source['sha'],
    'pdf_pages':pages,'cases':[],'status':'RUNNING','semantic_acceptance':False,
    'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
out=root/'evidence/priority-pages-api.json'
out.parent.mkdir(exist_ok=True)
try:
    for name,priority in [('beyond_actual_page_count',[pages+1]),('duplicate_existing_page',[existing,existing])]:
        before=counts();body={'purpose':'validation','priority_pages':priority}
        req=urllib.request.Request(a.base.rstrip('/')+'/v1/content-versions/'+str(a.content_version)+'/analyses',
            data=json.dumps(body).encode(),method='POST',headers={'Authorization':'Bearer '+token,
                'Content-Type':'application/json','Idempotency-Key':'invalid-priority:'+str(uuid.uuid4())})
        try:
            with urllib.request.urlopen(req,timeout=60) as r:code=r.status;response=json.load(r)
        except urllib.error.HTTPError as exc:code=exc.code;response=json.load(exc)
        after=counts()
        result={'case':name,'request':body,'http_status':code,'response':response,
            'pg_before':before,'pg_after':after,'no_new_job_or_generation':before==after}
        report['cases'].append(result)
        assert code==422 and response.get('detail')=='INVALID_PRIORITY_PAGES',result
        assert before==after,result
    report['status']='PASS'
except Exception as exc:
    report['status']='FAILED';report['error']=str(exc)
    raise
finally:
    report['checked_at']=datetime.now(timezone.utc).isoformat()
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
