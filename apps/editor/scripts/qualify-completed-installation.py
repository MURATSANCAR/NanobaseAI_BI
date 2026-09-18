#!/usr/bin/env python3
"""One-shot real-book backup/offline/restore qualification after a pinned run.

Never grades literature, changes source text, publishes a generation, retries a
failed analysis, or starts another analysis. Run on the connected Linux server.
"""
import fcntl
import hashlib
import ipaddress
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
run_file=root/os.environ.get('EDITOR_VERIFY_RUN_FILE','evidence/source-spans-run.json')
run=json.loads(run_file.read_text())
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
base='http://127.0.0.1:8810'
work=Path(os.environ.get('EDITOR_QUALIFICATION_ROOT',str(root.parent/'editor-qualifications')))/run['generation_id'][:8]
resume=os.environ.get('EDITOR_QUALIFICATION_RESUME')=='1'
work.mkdir(mode=0o700,parents=True,exist_ok=resume)
status=root/'evidence/installation-qualification-status.md'
report={'generation_id':run['generation_id'],'job_id':run['job_id'],
        'environment':'connected Linux host / real PDF / PostgreSQL',
        'work_directory':str(work),'steps':[],'semantic_acceptance':False}
target=None;target_started=False
if resume:
    previous=json.loads((work/'qualification.json').read_text())
    restore_started=any(s['stage']=='restore' for s in previous['steps'])
    initialized=any(s['stage']=='target_init' and s['state']=='PASS' for s in previous['steps'])
    if (previous['generation_id']!=run['generation_id'] or restore_started
            or ((work/'installation').exists() and not initialized)):
        raise RuntimeError('QUALIFICATION_RESUME_SCOPE_MISMATCH')
    report=previous


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


def available_subnets():
    ids=subprocess.check_output(['docker','network','ls','-q'],text=True).split()
    networks=json.loads(subprocess.check_output(['docker','network','inspect',*ids],text=True)) if ids else []
    used=[ipaddress.ip_network(c['Subnet']) for n in networks
          for c in ((n.get('IPAM') or {}).get('Config') or []) if c.get('Subnet')]
    requested=[os.environ.get('EDITOR_QUALIFICATION_'+name+'_SUBNET') for name in ('PRIVATE','INGRESS')]
    if any(requested):
        if not all(requested):raise RuntimeError('BOTH_QUALIFICATION_SUBNETS_REQUIRED')
        pair=[ipaddress.ip_network(value) for value in requested]
        if (any(net.version!=4 or not net.is_private for net in pair) or pair[0].overlaps(pair[1])
                or any(a.version==b.version and a.overlaps(b) for a in pair for b in used)):
            raise RuntimeError('QUALIFICATION_SUBNETS_INVALID_OR_IN_USE')
        return tuple(map(str,pair))
    for octet in range(50,250,2):
        pair=[ipaddress.ip_network(f'10.203.{n}.0/24') for n in (octet,octet+1)]
        if not any(a.version==b.version and a.overlaps(b) for a in pair for b in used):
            return tuple(map(str,pair))
    raise RuntimeError('NO_FREE_QUALIFICATION_SUBNETS')


try:
    execute('release_bytes',['python3','scripts/verify-release.py'])
    active_config=json.loads(subprocess.check_output(['docker','compose','config','--format','json'],text=True))
    active_env=active_config['services']['api'].get('environment',{})
    external=active_env.get('EDITOR_MODEL_BACKEND')=='vllm' or bool(active_env.get('EDITOR_OCR_VL_BASE_URL'))
    endpoints={key:os.environ.get('EDITOR_QUALIFY_'+key.removeprefix('EDITOR_'),'')
               for key in ('EDITOR_MODEL_BASE_URL','EDITOR_OCR_VL_BASE_URL')}
    if external and not all(endpoints.values()):
        raise RuntimeError('EXTERNAL_TARGET_MODEL_ENDPOINTS_REQUIRED')
    bundle_args=['python3','scripts/bundle.py',str(work/'offline'),'--external-models' if external else '--with-models']
    if os.environ.get('EDITOR_QUALIFY_OCR_VL')=='1':bundle_args.append('--with-ocr-vl')
    if resume and (work/'offline/release-manifest.json').exists():
        record('offline_bundle','REUSED','Hash ve imaj kontrolü offline_import aşamasında tekrarlanacak.')
    else:
        execute('offline_bundle',bundle_args,timeout=7200)
    manifest=json.loads((work/'offline/release-manifest.json').read_text())
    for name in manifest['files']:
        parts=Path(name).parts
        if any(p in ('secrets','evidence','node_modules','.git') for p in parts):
            raise RuntimeError('PRIVATE_OR_BUILD_FILES_IN_BUNDLE')
        if Path(name).name.startswith('.env') and Path(name).name!='.env.example':
            raise RuntimeError('PRIVATE_ENV_IN_BUNDLE')
    assert manifest['ocr_included'] is True
    if os.environ.get('EDITOR_QUALIFY_OCR_VL')=='1':assert manifest['ocr_vl_included'] is True
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
    if json.loads(run_file.read_text())!=run:
        raise RuntimeError('ACTIVE_RUN_CHANGED')
    active=subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',
        "SELECT count(*) FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')"],text=True).strip()
    if active!='0':raise RuntimeError('OTHER_ACTIVE_JOBS_NO_BACKUP_RESTART')
    # These networkless tools write artifacts outside the DB job queue. A backup
    # must not race a live OCR or document process, even after analysis completes.
    config=json.loads(subprocess.check_output(['docker','compose','config','--format','json'],text=True))
    record('wait_for_artifact_tools','WAITING')
    for _ in range(240):
        live=[]
        for service in ('ocr-vl','document'):
            live.extend(subprocess.check_output(['docker','ps','-q',
                '--filter','label=com.docker.compose.project='+config['name'],
                '--filter','label=com.docker.compose.service='+service],text=True).split())
        if not live:break
        time.sleep(30)
    else:raise RuntimeError('ARTIFACT_TOOLS_STILL_RUNNING')
    record('wait_for_artifact_tools','PASS')
    record('wait_for_pinned_analysis','PASS','İşleme tamamlandı; anlamsal kabul değil.')
    execute('source_api_pg',['python3','scripts/verify-source-pipeline.py'])
    if os.environ.get('EDITOR_QUALIFY_DERIVED')=='1':
        execute('derived_api_pg',['python3','scripts/verify-source-analysis.py',run['generation_id'],'--fragments'])
        execute('semantic_provenance',['python3','scripts/verify-semantic-provenance.py',run['generation_id']])
    execute('release_bytes_after_analysis',['python3','scripts/verify-release.py'])
    packaged=(work/'offline/editor/backend')
    for path in (root/'backend').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            if path.read_bytes()!=(packaged/path.relative_to(root/'backend')).read_bytes():
                raise RuntimeError('RELEASE_CHANGED_DURING_ANALYSIS')
    execute('source_isolation',['python3','scripts/verify-isolation.py'])
    if resume and (work/'backup/manifest.json').exists():
        from snapshot_reference import book_reference
        backup=json.loads((work/'backup/manifest.json').read_text())
        for name,expected in backup['files'].items():
            if name not in ('database.dump','artifacts.tar'):raise RuntimeError('INVALID_BACKUP_MEMBER')
            with (work/'backup'/name).open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=expected:raise RuntimeError('BACKUP_HASH_MISMATCH')
        if backup['book_reference']!=book_reference(config,backup['book_reference']['database'].keys()):raise RuntimeError('SOURCE_CHANGED_SINCE_BACKUP')
        record('backup','REUSED','Hash ve canlı kaynak/kitap kaydı eşliği yeniden doğrulandı.')
    else:
        execute('backup',['python3','scripts/backup.py',str(work/'backup')])
    target=work/'installation'
    if target.exists():
        for path in (packaged).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                if path.read_bytes()!=(target/'backend'/path.relative_to(packaged)).read_bytes():
                    raise RuntimeError('TARGET_RELEASE_CHANGED')
        record('target_init','REUSED','Restore başlamamış hedefin uygulama dosyaları paketle eşleşti.')
    else:
        shutil.copytree(work/'offline/editor',target)
        execute('target_init',['python3','scripts/init.py'],cwd=target)
    # Different releases can qualify the same immutable generation. Never reuse
    # volumes retained as evidence by an earlier qualification of that generation.
    project='editor-qualification-'+run['generation_id'][:8]+'-'+hashlib.sha256(str(work.resolve()).encode()).hexdigest()[:6]
    private_subnet,ingress_subnet=available_subnets()
    port=os.environ.get('EDITOR_QUALIFICATION_PORT','18810')
    settings(target/'.env',{'COMPOSE_PROJECT_NAME':project,'EDITOR_PORT':port,
        'EDITOR_METRICS_PORT':os.environ.get('EDITOR_QUALIFICATION_METRICS_PORT','19096'),
        'EDITOR_PRIVATE_SUBNET':private_subnet,'EDITOR_INGRESS_SUBNET':ingress_subnet,
        **(endpoints if external else {})})
    record('target_network','CONFIGURED',json.dumps({'private_subnet':private_subnet,'ingress_subnet':ingress_subnet,'api_port':port,'external_models':external}))
    target_started=True
    execute('restore',['python3','scripts/restore.py',str(work/'backup'),project],cwd=target,timeout=7200)
    (target/'evidence').mkdir(exist_ok=True,mode=0o700)
    (target/'evidence/source-spans-run.json').write_text(json.dumps(run))
    env={**os.environ,'EDITOR_VERIFY_BASE_URL':'http://127.0.0.1:'+port,
         'EDITOR_VERIFY_RUN_FILE':'evidence/source-spans-run.json'}
    execute('restored_source_api_pg',['python3','scripts/verify-source-pipeline.py'],cwd=target,env=env)
    if os.environ.get('EDITOR_QUALIFY_DERIVED')=='1':
        execute('restored_derived_api_pg',['python3','scripts/verify-source-analysis.py',run['generation_id'],'--fragments'],cwd=target,env=env)
        execute('restored_semantic_provenance',['python3','scripts/verify-semantic-provenance.py',run['generation_id']],cwd=target,env=env)
    if os.environ.get('EDITOR_QUALIFY_OCR_VL')=='1':
        env['EDITOR_VERIFY_OCR_VL']='1'
        execute('restored_ocr_vl_api_pg',['python3','scripts/verify-ocr-vl-review.py'],cwd=target,env=env)
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
