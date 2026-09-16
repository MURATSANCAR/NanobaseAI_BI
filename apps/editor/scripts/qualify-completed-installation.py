#!/usr/bin/env python3
"""One-shot real-book backup/offline/restore qualification after a pinned run.

Never grades literature, changes source text, publishes a generation, retries a
failed analysis, or starts another analysis. Run on the connected Linux server.
"""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[1];os.chdir(root)
lock=(root/'evidence/installation-qualification.lock').open('w')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
run=json.loads((root/'evidence/source-spans-run.json').read_text())
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
base='http://127.0.0.1:8810'
work=root.parent/('editor-qualification-'+run['generation_id'][:8])
work.mkdir(mode=0o700,exist_ok=False)
status=root/'evidence/installation-qualification-status.md'
report={'generation_id':run['generation_id'],'job_id':run['job_id'],
        'environment':'connected Linux host / real PDF / PostgreSQL',
        'work_directory':str(work),'steps':[],'semantic_acceptance':False}
target=None;target_started=False


def record(stage,state,detail=''):
    entry={'at':datetime.now(timezone.utc).isoformat(),'stage':stage,'state':state,'detail':detail}
    report['steps'].append(entry)
    (work/'qualification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    status.write_text('# Kurulum doğrulaması\n\n'+
        f'Nesil: `{run["generation_id"]}`\n\n'+
        '\n'.join(f'- {s["at"]} — {s["stage"]}: **{s["state"]}** {s["detail"]}' for s in report['steps'])+
        '\n\nAnlamsal kitap kabulü değildir; kitap içeriği veya kabul kararı değiştirilmez.\n')
    print(json.dumps(entry,ensure_ascii=False),flush=True)


def execute(name,command,cwd=root,env=None,timeout=3600):
    record(name,'RUNNING')
    with (work/(name+'.log')).open('w') as log:
        subprocess.run(command,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,
                       check=True,timeout=timeout)
    record(name,'PASS')


def settings(path,updates):
    lines=path.read_text().splitlines()
    lines=[line for line in lines if not any(line.startswith(k+'=') for k in updates)]
    path.write_text('\n'.join(lines+[k+'='+v for k,v in updates.items()])+'\n')


try:
    execute('release_bytes',['python3','scripts/verify-release.py'])
    execute('offline_bundle',['python3','scripts/bundle.py',str(work/'offline'),'--with-models'],timeout=7200)
    manifest=json.loads((work/'offline/release-manifest.json').read_text())
    for name in manifest['files']:
        parts=Path(name).parts
        if any(p in ('secrets','evidence','node_modules','.git') for p in parts):
            raise RuntimeError('PRIVATE_OR_BUILD_FILES_IN_BUNDLE')
        if Path(name).name.startswith('.env') and Path(name).name!='.env.example':
            raise RuntimeError('PRIVATE_ENV_IN_BUNDLE')
    assert manifest['ocr_included'] is True
    execute('offline_import',['python3','scripts/import-bundle.py',str(work/'offline')],timeout=7200)
    record('wait_for_pinned_analysis','WAITING')
    start=time.monotonic();failures=0
    while time.monotonic()-start<86400:
        try:
            req=urllib.request.Request(base+'/v1/jobs/'+run['job_id'],headers=headers)
            with urllib.request.urlopen(req,timeout=30) as response:job=json.load(response)
            failures=0
        except OSError:
            failures+=1
            if failures>=10:raise RuntimeError('API_UNAVAILABLE')
            time.sleep(30);continue
        if job['status'] in ('FAILED','CANCELLED'):
            raise RuntimeError('ANALYSIS_'+job['status']+':'+str(job.get('error_code')))
        if job['status']=='COMPLETED':break
        time.sleep(30)
    else:raise RuntimeError('ANALYSIS_NOT_FINISHED_WITHIN_24_HOURS')
    if json.loads((root/'evidence/source-spans-run.json').read_text())!=run:
        raise RuntimeError('ACTIVE_RUN_CHANGED')
    active=subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',
        "SELECT count(*) FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')"],text=True).strip()
    if active!='0':raise RuntimeError('OTHER_ACTIVE_JOBS_NO_BACKUP_RESTART')
    record('wait_for_pinned_analysis','PASS','İşleme tamamlandı; anlamsal kabul değil.')
    execute('source_api_pg',['python3','scripts/verify-source-pipeline.py'])
    execute('release_bytes_after_analysis',['python3','scripts/verify-release.py'])
    packaged=(work/'offline/editor/backend')
    for path in (root/'backend').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            if path.read_bytes()!=(packaged/path.relative_to(root/'backend')).read_bytes():
                raise RuntimeError('RELEASE_CHANGED_DURING_ANALYSIS')
    execute('source_isolation',['python3','scripts/verify-isolation.py'])
    execute('backup',['python3','scripts/backup.py',str(work/'backup')])
    target=work/'installation'
    shutil.copytree(work/'offline/editor',target)
    execute('target_init',['python3','scripts/init.py'],cwd=target)
    project='editor-qualification-'+run['generation_id'][:8]
    settings(target/'.env',{'COMPOSE_PROJECT_NAME':project,'EDITOR_PORT':'18810','EDITOR_METRICS_PORT':'19096',
        'EDITOR_PRIVATE_SUBNET':'10.203.50.0/24','EDITOR_INGRESS_SUBNET':'10.203.51.0/24'})
    target_started=True
    execute('restore',['python3','scripts/restore.py',str(work/'backup'),project],cwd=target,timeout=7200)
    (target/'evidence').mkdir(exist_ok=True,mode=0o700)
    (target/'evidence/source-spans-run.json').write_text(json.dumps(run))
    env={**os.environ,'EDITOR_VERIFY_BASE_URL':'http://127.0.0.1:18810',
         'EDITOR_VERIFY_RUN_FILE':'evidence/source-spans-run.json'}
    execute('restored_source_api_pg',['python3','scripts/verify-source-pipeline.py'],cwd=target,env=env)
    # Browser tooling is an external test dependency, not part of the customer package.
    shutil.copytree(root/'runtime/browser-check',target/'runtime/browser-check')
    execute('restored_mobile_ui',['node','scripts/verify-review-ui.cjs'],cwd=target,env=env)
    record('qualification','PASS','Yedek/restore ve paket doğrulandı; sentez/arama/soru kalitesi DOĞRULANAMADI.')
except Exception as exc:
    record('qualification','FAILED',type(exc).__name__+': '+str(exc))
    raise
finally:
    if target_started and target is not None:
        # Retain target volumes and evidence for review; stop duplicate services.
        with (work/'target-stop.log').open('w') as log:
            stopped=subprocess.run(['docker','compose','stop'],cwd=target,stdout=log,stderr=subprocess.STDOUT)
        record('target_services','STOPPED' if stopped.returncode==0 else 'STOP_FAILED','Veriler ve kanıtlar korundu.')
