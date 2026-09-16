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
import subprocess
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[1]
lock=(root/'evidence/source-pages-follow.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
run=json.loads((root/'evidence/source-spans-run.json').read_text())
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
(root/'evidence/source-pages-follow.pid').write_text(str(os.getpid()))
previous=None;last_change=time.monotonic();last_audited=-1;last_audit_attempt=0
for attempt in range(4320):
    try:
        req=urllib.request.Request('http://127.0.0.1:8810/v1/jobs/'+run['job_id'],headers=headers)
        with urllib.request.urlopen(req,timeout=30) as response: job=json.load(response)
        report={k:job[k] for k in ('id','status','progress','counts','error_code')}
        line=json.dumps(report,ensure_ascii=False)
        if line!=previous:
            print(json.dumps({'observed_at':datetime.now(timezone.utc).isoformat(),**report}),flush=True)
            previous=line;last_change=time.monotonic()
        counts={r['kind']:r['count'] for r in job['counts']}
        terminal=job['status'] in ('COMPLETED','FAILED','CANCELLED')
        milestone=counts.get('page_checks',0)//10
        if terminal or (milestone>last_audited and time.monotonic()-last_audit_attempt>300):
            last_audit_attempt=time.monotonic()
            path=root/'evidence'/f'source-audit-{run["generation_id"]}-{counts.get("page_checks",0):04}.log'
            with path.open('w') as stream:
                try:
                    result=subprocess.run(['python3',str(root/'scripts/verify-source-pipeline.py')],
                        stdout=stream,stderr=subprocess.STDOUT,timeout=900)
                    passed=result.returncode==0
                except subprocess.TimeoutExpired:passed=False
            print(json.dumps({'event':'structural_audit','passed':passed,'evidence':str(path),
                              'semantic_acceptance':False}),flush=True)
            if passed:last_audited=milestone
        now=datetime.now(timezone.utc).isoformat()
        summary=(f'# Editör canlı koşu\n\nSon gözlem: {now}\n\n'
            f'- İş: `{run["job_id"]}`\n- Nesil: `{run["generation_id"]}`\n'
            f'- İşlem: **{job["status"]}**\n'
            f'- OCR: {counts.get("page_readings",0)} / {job["source_coverage"]["expected_pages"]}\n'
            f'- Sayfa kontrol kaydı: {counts.get("page_checks",0)}\n'
            f'- Metin bölgesi: {counts.get("source_spans",0)}\n'
            f'- Son hata: {job.get("error_code")}\n'
            f'- Son ilerlemeden beri: {int(time.monotonic()-last_change)} saniye\n\n'
            'İşlem tamamlanması anlamsal kabul değildir. Bu gözlemci kaynak/karar değiştirmez. '
            'API/PG kayıt denetimi her 10 sayfada ve terminal durumda çalışır. '
            'NEEDS_REVIEW durumundan otomatik yayın/sentez yapılmaz.\n')
        target=root/'evidence/source-pages-status.md'
        temporary=target.with_suffix('.tmp');temporary.write_text(summary);temporary.replace(target)
        if terminal:break
    except (OSError,urllib.error.URLError,http.client.HTTPException) as exc:
        print(json.dumps({'observer_retry':type(exc).__name__}),flush=True)
    time.sleep(20)
