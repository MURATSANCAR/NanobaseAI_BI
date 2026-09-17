#!/usr/bin/env python3
"""Pause the real OCR reader briefly; verify backup refuses before stopping the API."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1];os.chdir(root)
requests=json.loads((root/'evidence/ocr-vl-pilot-input.json').read_text())
assert requests and all(r['spans'] for r in requests),'REAL_OCR_INPUT_REQUIRED'
name='editor-backup-guard-'+uuid.uuid4().hex[:12]
destination=root/'evidence'/name
def ready():
    with urllib.request.urlopen('http://127.0.0.1:8810/health/ready',timeout=10) as response:
        assert response.status==200
ready();paused=False
with (root/'evidence/backup-guard-real-reader.log').open('w') as log, (root/'evidence/ocr-vl-pilot-input.json').open() as source:
    process=subprocess.Popen(['docker','compose','-f','compose.yaml','-f','compose.ocr-vl.yaml','--profile','ocr-vl',
        'run','--rm','--no-deps','--name',name,'-T','ocr-vl'],stdin=source,stdout=log,stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            state=subprocess.run(['docker','inspect','--format','{{.State.Running}}',name],capture_output=True,text=True)
            if state.returncode==0 and state.stdout.strip()=='true':break
            if process.poll() is not None:raise RuntimeError('READER_EXITED_BEFORE_CHECK')
            time.sleep(.5)
        else:raise RuntimeError('READER_NOT_STARTED')
        subprocess.run(['docker','pause',name],check=True,stdout=subprocess.DEVNULL);paused=True
        result=subprocess.run(['python3','scripts/backup.py',str(destination)],capture_output=True,text=True,timeout=60)
        assert result.returncode!=0 and 'Finish active artifact tools' in result.stderr,'BACKUP_DID_NOT_REFUSE'
        assert not (destination/'database.dump').exists() and not (destination/'manifest.json').exists()
        ready()
    finally:
        if paused:subprocess.run(['docker','unpause',name],check=True,stdout=subprocess.DEVNULL)
        try:process.wait(timeout=180)
        except subprocess.TimeoutExpired:
            subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            process.wait(timeout=30)
            raise
        finally:subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    assert process.returncode==0,'REAL_READER_FAILED'
report={'real_source_input':True,'active_ocr_reader_blocked_backup':True,
        'api_remained_ready':True,'dump_not_started':True,'reader_resumed_and_completed':True,
        'semantic_acceptance':False}
(root/'evidence/backup-writer-guard-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
