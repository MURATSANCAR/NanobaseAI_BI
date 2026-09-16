#!/usr/bin/env python3
"""One real job's resource/health observations; health is not a BI/Legal SLO test."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

root=Path(__file__).resolve().parents[1]
os.chdir(root)
run=json.loads((root/'evidence/reference-book-run.json').read_text())
job=run['job']['job_id']
token=(root/'secrets/api_token').read_text().strip()
destination=root/'evidence'/('resources-'+job+'.jsonl')
started=time.monotonic()
with destination.open('a') as output:
    while time.monotonic()-started<86400:
        row={'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'job_id':job}
        try:
            request=urllib.request.Request('http://127.0.0.1:8810/v1/jobs/'+job,
                                           headers={'Authorization':'Bearer '+token})
            with urllib.request.urlopen(request,timeout=15) as response: state=json.load(response)
            row.update({key:state[key] for key in ('status','progress','counts')})
            ids=subprocess.check_output(['docker','compose','ps','-q','llm','worker','api'],text=True).split()
            if ids:
                stats=subprocess.check_output(['docker','stats','--no-stream','--format','{{json .}}',*ids],text=True,timeout=20)
                row['containers']=[json.loads(line) for line in stats.splitlines()]
            row['health_only_not_business_slo']=[]
            for port,path in ((8076,'/health'),(8078,'/health'),(8795,'/health')):
                before=time.monotonic()
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}',timeout=5) as response:
                        status=response.status
                except Exception as exc: status=type(exc).__name__
                row['health_only_not_business_slo'].append({'port':port,'status':status,'seconds':round(time.monotonic()-before,4)})
        except Exception as exc: row['observation_error']=type(exc).__name__
        output.write(json.dumps(row,ensure_ascii=False)+'\n'); output.flush()
        if row.get('status') in ('COMPLETED','FAILED','CANCELLED'): break
        time.sleep(30)
print(destination)
