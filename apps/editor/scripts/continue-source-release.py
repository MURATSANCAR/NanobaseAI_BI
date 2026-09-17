#!/usr/bin/env python3
"""Explicitly invoked, fail-closed continuation on an isolated real installation.

Does not install an automation, repair source data, retry failed analyses, migrate
schemas, or pull/build images. The operator supplies a prebuilt immutable image.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

parser=argparse.ArgumentParser()
for option in ('base','run-file','next-run-file','release','expected-current-tree','target-image-id','priority-pages'):
    parser.add_argument('--'+option,required=True)
parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
parser.add_argument('--observe-only',action='store_true',help=argparse.SUPPRESS)
args=parser.parse_args();root=Path(args.root).resolve();os.chdir(root)
assert re.fullmatch(r'[a-f0-9]{64}',args.expected_current_tree)
assert re.fullmatch(r'sha256:[a-f0-9]{64}',args.target_image_id)
assert re.fullmatch(r'[a-zA-Z0-9_.-]+',args.release)
priorities=json.loads(args.priority_pages)
assert isinstance(priorities,list) and all(type(n) is int and n>0 for n in priorities) and len(set(priorities))==len(priorities)
run_path=Path(args.run_file).resolve();next_path=Path(args.next_run_file).resolve()
assert run_path!=next_path
private=root/'runtime'/'release-continuation';private.mkdir(parents=True,exist_ok=True,mode=0o700)
checkpoint=private/(args.release+('-observer' if args.observe_only else '')+'.json')
lock=(private/(args.release+('-observer' if args.observe_only else '')+'.lock')).open('a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
state=json.loads(checkpoint.read_text()) if checkpoint.exists() else {}
identity={'base':args.base,'run_file':str(run_path),'next_run_file':str(next_path),'release':args.release,
          'expected_current_tree':args.expected_current_tree,'target_image_id':args.target_image_id,'priority_pages':priorities}
assert not state or state['identity']==identity,'CHECKPOINT_ARGUMENTS_CHANGED'
state.setdefault('identity',identity)
token=(root/'secrets/api_token').read_text().strip()


def atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.'+str(uuid.uuid4())+'.tmp')
    with temporary.open('x') as stream:
        os.chmod(temporary,0o600);stream.write(value);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


def mark(stage,**fields):
    state.update(fields);state['stage']=stage;state['updated_at']=time.time()
    atomic(checkpoint,json.dumps(state,indent=2))
    print(json.dumps({'stage':stage,**fields}),flush=True)


def command(parts,timeout=120):
    # Output may contain configuration secrets. Never echo command output on error.
    proc=subprocess.run(parts,capture_output=True,text=True,timeout=timeout)
    if proc.returncode:raise RuntimeError('COMMAND_FAILED:'+parts[0]+':'+str(proc.returncode))
    return proc.stdout.strip()


def api(path,body=None,key=None):
    headers={'Authorization':'Bearer '+token}
    if body is not None:headers.update({'Content-Type':'application/json','Idempotency-Key':key})
    request=urllib.request.Request(args.base.rstrip('/')+path,headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    for attempt in range(7):
        try:
            with urllib.request.urlopen(request,timeout=60) as response:return json.load(response)
        except (urllib.error.URLError, TimeoutError) as exc:
            transient=not isinstance(exc,urllib.error.HTTPError) or exc.code in (429,502,503,504)
            if not transient or attempt==6:
                if isinstance(exc,urllib.error.HTTPError):
                    raise RuntimeError('API_HTTP_'+str(exc.code)) from None
                raise RuntimeError('API_TRANSPORT_UNAVAILABLE') from None
            # GET and this helper's keyed POST are safe to repeat after a lost
            # response. Never mint a replacement key or a duplicate analysis.
            time.sleep(min(2**attempt,15))


def wait_job(run,label):
    start_key=label+'_started_at';state.setdefault(start_key,time.time());mark(label)
    while time.time()-state[start_key]<43200:
        job=api('/v1/jobs/'+str(uuid.UUID(run['job_id'])))
        assert job['generation_id']==run['generation_id'],'JOB_GENERATION_MISMATCH'
        if job['status']=='COMPLETED':return
        if job['status'] in ('FAILED','CANCELLED'):raise RuntimeError(label+'_'+job['status'])
        if job['status'] not in ('QUEUED','RUNNING'):raise RuntimeError('UNEXPECTED_JOB_STATUS')
        time.sleep(20)
    raise RuntimeError(label+'_DEADLINE_EXCEEDED')


def no_active_jobs():
    result=command(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',
        "SELECT count(*) FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')"])
    assert result=='0','ACTIVE_JOB_PREVENTS_RELEASE_SWITCH'


def running_identity(service):
    container=command(['docker','compose','ps','-q',service]);assert container and '\n' not in container
    image=command(['docker','inspect','--format','{{.Image}}',container])
    code="import hashlib,json,pathlib;r=pathlib.Path('/app');d={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob('*') if p.is_file() and '__pycache__' not in p.parts};print(hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest())"
    tree=command(['docker','exec',container,'python','-c',code])
    return {'image':image,'tree':tree}


def verify(runfile):
    environment=dict(os.environ,EDITOR_VERIFY_BASE_URL=args.base,EDITOR_VERIFY_ROOT=str(root),
                     EDITOR_VERIFY_RUN_FILE=str(runfile),EDITOR_VERIFY_WEB='1')
    logroot=root/'evidence'/('continuation-'+args.release);logroot.mkdir(parents=True,exist_ok=True)
    for script in ('verify-source-pipeline.py','verify-regional-source.py','verify-character-evidence.py','verify-narrative-coverage.py'):
        with (logroot/(script+'.log')).open('a') as log:
            proc=subprocess.run([sys.executable,str(root/'scripts'/script)],env=environment,stdout=log,stderr=log,timeout=3600)
        if proc.returncode:raise RuntimeError('VERIFICATION_FAILED:'+script)
    environment.update(EDITOR_VERIFY_REGIONAL_SOURCE='1',EDITOR_VERIFY_VISUAL_COVERAGE='1')
    with (logroot/'verify-review-ui.cjs.log').open('a') as log:
        proc=subprocess.run(['node',str(root/'scripts/verify-review-ui.cjs')],env=environment,stdout=log,stderr=log,timeout=1800)
    if proc.returncode:raise RuntimeError('VERIFICATION_FAILED:verify-review-ui.cjs')


try:
    config=json.loads(command(['docker','compose','config','--format','json']))
    assert 'qualification' in config['name'],'ISOLATED_QUALIFICATION_REQUIRED'
    if args.observe_only:
        run=json.loads(next_path.read_text());wait_job(run,'OBSERVING_NEXT_JOB');verify(next_path)
        mark('COMPLETE',generation_id=run['generation_id'],semantic_acceptance=False)
    else:
        previous=json.loads(run_path.read_text())
        assert re.fullmatch(r'[0-9a-f-]{36}',previous['generation_id'])
        actual_parent=api('/v1/generations/'+str(uuid.UUID(previous['generation_id'])))
        assert actual_parent['content_version_id']==previous['content_version_id'],'PARENT_CONTENT_VERSION_MISMATCH'
        installed=state.get('target_ready',False)
        if not installed:
            wait_job(previous,'WAITING_FOR_CURRENT_JOB')
            no_active_jobs()
            pin=command(['docker','image','inspect','--format','{{.Id}}',args.target_image_id])
            assert pin==args.target_image_id,'TARGET_IMAGE_PIN_MISMATCH'
            current={service:running_identity(service) for service in ('api','worker')}
            # Resume after an interrupted deployment only when the prior checkpoint
            # records that this exact target image switch was already authorized.
            if not state.get('switch_started'):
                assert all(v['tree']==args.expected_current_tree for v in current.values()),'CURRENT_BACKEND_TREE_MISMATCH'
                assert len({v['image'] for v in current.values()})==1,'CURRENT_SERVICE_IMAGES_DIFFER'
                mark('SWITCH_PREPARED',original_services=current,switch_started=True)
            else:
                assert all(v['image'] in (state['original_services'][s]['image'],args.target_image_id) for s,v in current.items()),'UNEXPECTED_RESUME_IMAGE'
            feature=root/'compose.feature.yaml';envfile=root/'.env'
            feature_data=json.loads(feature.read_text());env=envfile.read_text()
            for service in ('api','worker','migrate','storage-init'):
                assert service in feature_data['services'];feature_data['services'][service]['image']=args.target_image_id
            assert len(re.findall(r'^EDITOR_RELEASE=.*$',env,re.M))==1,'RELEASE_ENV_MISSING_OR_DUPLICATE'
            env=re.sub(r'^EDITOR_RELEASE=.*$','EDITOR_RELEASE='+args.release,env,flags=re.M)
            no_active_jobs()
            atomic(feature,json.dumps(feature_data,indent=2));atomic(envfile,env)
            command(['docker','compose','up','-d','--no-deps','--pull','never','api','worker'],timeout=600)
            deadline=time.time()+180
            while True:
                try:
                    api('/health/ready');break
                except (RuntimeError,urllib.error.URLError):
                    if time.time()>=deadline:raise RuntimeError('NEW_API_READINESS_TIMEOUT') from None
                    time.sleep(5)
            after={s:running_identity(s) for s in ('api','worker')}
            assert all(v['image']==args.target_image_id for v in after.values())
            assert len({v['tree'] for v in after.values()})==1,'TARGET_SERVICE_TREES_DIFFER'
            environment=dict(os.environ,EDITOR_VERIFY_WEB='1')
            proc=subprocess.run([sys.executable,str(root/'scripts/verify-release.py')],env=environment,capture_output=True,text=True,timeout=180)
            assert proc.returncode==0,'TARGET_RELEASE_OR_WEB_BYTES_MISMATCH'
            assert api('/v1/system')['release']==args.release,'TARGET_RELEASE_LABEL_MISMATCH'
            mark('TARGET_READY',target_ready=True,target_services=after)
        assert all(running_identity(s)['image']==args.target_image_id for s in ('api','worker')),'TARGET_CHANGED'
        if next_path.exists():
            next_run=json.loads(next_path.read_text())
            assert next_run['parent_generation_id']==previous['generation_id'] and next_run['release']==args.release
            assert next_run['content_version_id']==previous['content_version_id'] and next_run['priority_pages']==priorities
        else:
            if not state.get('analysis_requested'):no_active_jobs()
            key='release-continuation:'+args.release+':'+previous['generation_id']
            mark('REQUESTING_NEXT_ANALYSIS',analysis_requested=True,idempotency_key=key)
            response=api('/v1/content-versions/'+str(uuid.UUID(previous['content_version_id']))+'/analyses',
                         {'purpose':'validation','reuse_measurements_from':previous['generation_id'],'priority_pages':priorities},key)
            next_run={**response,'parent_generation_id':previous['generation_id'],'release':args.release,
                      'content_version_id':previous['content_version_id'],'priority_pages':priorities,'api':args.base}
            atomic(next_path,json.dumps(next_run,indent=2))
        mark('NEXT_JOB_STARTED',job_id=next_run['job_id'],generation_id=next_run['generation_id'])
        # Independent observer owns a separate lock/checkpoint and never deploys.
        observer_checkpoint=private/(args.release+'-observer.json')
        observer_lock=(private/(args.release+'-observer.lock')).open('a')
        try:
            fcntl.flock(observer_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(observer_lock,fcntl.LOCK_UN)
            observer_running=False
        except BlockingIOError:
            observer_running=True
        finally:observer_lock.close()
        if observer_running:
            mark('EXISTING_OBSERVER_RUNNING')
            deadline=time.time()+43200
            while time.time()<deadline:
                progress=json.loads(observer_checkpoint.read_text()) if observer_checkpoint.exists() else {}
                if progress.get('stage')=='COMPLETE':break
                if progress.get('stage')=='FAILED':raise RuntimeError('EXISTING_OBSERVER_FAILED')
                time.sleep(20)
            else:raise RuntimeError('EXISTING_OBSERVER_DEADLINE_EXCEEDED')
        else:
            observer=[sys.executable,str(Path(__file__).resolve()),*sys.argv[1:],'--observe-only']
            with (private/(args.release+'-observer.log')).open('a') as log:
                child=subprocess.Popen(observer,stdout=log,stderr=log,start_new_session=True)
                mark('OBSERVER_STARTED',observer_pid=child.pid)
                if child.wait()!=0:raise RuntimeError('OBSERVER_OR_FINAL_VERIFICATION_FAILED')
        mark('COMPLETE',semantic_acceptance=False)
except Exception as exc:
    # Do not serialize arbitrary exception messages: external tools may include secrets.
    reason=str(exc) if isinstance(exc,(RuntimeError,AssertionError)) and re.fullmatch(r'[A-Za-z0-9_:.-]{1,200}',str(exc)) else type(exc).__name__
    mark('FAILED',error=reason,source_or_review_writes=0)
    raise SystemExit(1)
