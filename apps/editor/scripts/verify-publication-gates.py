#!/usr/bin/env python3
"""Real API/PG checks: unqualified book output must not publish or answer.

Only rejection paths are exercised; no content or editorial decisions are written.
"""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.error
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
for mode in ('editor_preview','published'):
    rejected('/v1/questions',{'generation_id':gen,'question':'Bu kitabın ana karakterleri kimler?','mode':mode},409,'GENERATION_NOT_READY')
rejected('/v1/generations/'+gen+'/activate',{'purpose':'validation'},409,'GENERATION_NOT_VALIDATED')
after=state()
assert after['status']!='ACTIVE' and before['reviews']==after['reviews'] and before['questions']==after['questions']
report={'generation_id':gen,'checked_at':datetime.now(timezone.utc).isoformat(),
    'api':base,'checks':checks,'database_before':before,'database_after':after,
    'editorial_decisions_written':0,'question_jobs_created':0,'semantic_acceptance':False}
with (root/'evidence'/('publication-gates-'+gen+'.json')).open('x') as stream:
    json.dump(report,stream,ensure_ascii=False,indent=2)
print(json.dumps(report,ensure_ascii=False,indent=2))
