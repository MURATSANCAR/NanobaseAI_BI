#!/usr/bin/env python3
"""Real API/PG checks: unqualified book output must not publish.

Only rejection paths are exercised; no content or editorial decisions are written.
"""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.error
import uuid
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/os.environ.get('EDITOR_VERIFY_RUN_FILE','evidence/source-spans-run.json')).read_text());gen=run['generation_id']
base=os.environ.get('EDITOR_VERIFY_BASE_URL','http://127.0.0.1:8810')
token=(root/'secrets/api_token').read_text().strip()


def state():
    query="SELECT json_build_object('status',status,'reviews',(SELECT count(*) FROM editor.reviews WHERE generation_id=g.id),'questions',(SELECT count(*) FROM editor.jobs WHERE generation_id=g.id AND task='question')) FROM editor.generations g WHERE id='"+gen+"'"
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))


def rejected(path,body,code,detail=None,authenticated=True):
    headers={'Content-Type':'application/json','Idempotency-Key':'publication-gate-'+gen+'-'+str(len(checks))}
    if authenticated:headers['Authorization']='Bearer '+token
    request=urllib.request.Request(base+path,headers=headers,data=json.dumps(body).encode() if body else None)
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            raise AssertionError('UNQUALIFIED_REQUEST_ACCEPTED:'+str(response.status))
    except urllib.error.HTTPError as exc:
        value=json.loads(exc.read())
        assert exc.code==code,(exc.code,value)
        if detail:assert value['detail']==detail,value
        checks.append({'path':path,'status':exc.code,'detail':value.get('detail')})


before=state()
assert before['status'] in ('BUILDING','NEEDS_REVIEW'), 'Do not probe mutation paths on an accepted generation'
checks=[]
rejected('/v1/generations/'+gen, None,401,authenticated=False)
preview=None
try:
    request=urllib.request.Request(base+'/v1/generations/'+gen+'/source-preview',headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(request,timeout=60) as response:preview=json.load(response)
except urllib.error.HTTPError as exc:
    # Older installations have no dedicated source-preview capability route.
    if exc.code not in (404,422):raise
if preview is not None:
    assert type(preview.get('ready')) is bool and preview.get('scope')=='PARTIAL_SOURCE_SUPPORTED_DRAFT'
    assert preview.get('semantic_acceptance',False) is False and preview.get('complete_book',False) is False
    checks.append({'path':'/v1/generations/'+gen+'/source-preview','status':200,'capability':preview})
    rejected('/v1/questions',{'generation_id':gen,'question':'Bu kitabın ana karakterleri kimler?','mode':'published'},409,'EDITOR_REVIEW_REQUIRED')
    if not preview['ready']:
        rejected('/v1/questions',{'generation_id':gen,'question':'Bu kitabın ana karakterleri kimler?','mode':'editor_preview'},409,'SOURCE_PREVIEW_NOT_READY')
    # A ready, limited editor preview is intentionally available. Its positive
    # real-job/answer acceptance is separate; this rejection-only probe creates none.
else:
    for mode in ('editor_preview','published'):
        rejected('/v1/questions',{'generation_id':gen,'question':'Bu kitabın ana karakterleri kimler?','mode':mode},409,'GENERATION_NOT_READY')
rejected('/v1/generations/'+gen+'/activate',{'purpose':'validation'},409,'GENERATION_NOT_VALIDATED')
after=state()
assert after['status']!='ACTIVE' and before['reviews']==after['reviews'] and before['questions']==after['questions']
report={'generation_id':gen,'checked_at':datetime.now(timezone.utc).isoformat(),
    'api':base,'checks':checks,'database_before':before,'database_after':after,
    'editorial_decisions_written':0,'question_jobs_created':0,'semantic_acceptance':False,
    'verification_id':str(uuid.uuid4()),'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
path=root/'evidence'/('publication-gates-'+gen+'-'+report['verification_id']+'.json')
report['evidence']=str(path)
with path.open('x') as stream:
    json.dump(report,stream,ensure_ascii=False,indent=2)
print(json.dumps(report,ensure_ascii=False,indent=2))
