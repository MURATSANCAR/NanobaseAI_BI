#!/usr/bin/env python3
"""Observe the new run. Never enqueue questions or change source/acceptance records."""
import fcntl
import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error
import http.client

root=Path(__file__).resolve().parents[1]
lock=(root/'evidence/source-pages-follow.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
run=json.loads((root/'evidence/source-spans-run.json').read_text())
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
(root/'evidence/source-pages-follow.pid').write_text(str(os.getpid()))
previous=None
for attempt in range(4320):
    try:
        req=urllib.request.Request('http://127.0.0.1:8810/v1/jobs/'+run['job_id'],headers=headers)
        with urllib.request.urlopen(req,timeout=30) as response: job=json.load(response)
        report={k:job[k] for k in ('id','status','progress','counts','error_code')}
        line=json.dumps(report,ensure_ascii=False)
        if line!=previous: print(line,flush=True);previous=line
        if job['status'] in ('COMPLETED','FAILED','CANCELLED'):break
    except (OSError,urllib.error.URLError,http.client.HTTPException) as exc:
        print(json.dumps({'observer_retry':type(exc).__name__}),flush=True)
    time.sleep(20)
