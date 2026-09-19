#!/usr/bin/env python3
"""Real cold GPU installation from packaged bytes, with restoration of live runners.

Run only after application jobs have finished. Model idleness and other GPU
processes are checked again here. This performs a maintenance restart, never
modifies a book, and never treats successful inference as semantic acceptance.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import signal
import subprocess
import time
import urllib.request

p=argparse.ArgumentParser()
for name in ('bundle','output','verification-script','visual-artifact','fragment-artifact','pair-artifact'):
    p.add_argument('--'+name,required=True)
p.add_argument('--live-qwen',default='qwen38-27b')
p.add_argument('--live-ocr',default='paddleocr-vl')
p.add_argument('--live-gateway',default='paddleocr-gateway')
args=p.parse_args()
bundle=Path(args.bundle).resolve();out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
lock=Path('/tmp/editor-gpu-offline-qualification.lock').open('a')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
project='editor-gpu-cold-'+hashlib.sha256(str(out).encode()).hexdigest()[:10]
env={**os.environ,'COMPOSE_PROJECT_NAME':project,'GPU_BIND_ADDRESS':'127.0.0.1',
     'QWEN_PORT':'18001','OCR_PORT':'18010','OCR_IDLE_SECONDS':'600'}
overlay=out/'offline-network.json';overlay.write_text(json.dumps({'networks':{'default':{'internal':True}}}))
compose=['docker','compose','-f',str(bundle/'compose.yaml'),'-f',str(overlay)]
report={'started_at':time.time(),'bundle':str(bundle),'project':project,'stages':[],
        'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'shared_verifier_sha256':hashlib.sha256(Path(args.verification_script).read_bytes()).hexdigest(),
        'application_writes':0,'semantic_acceptance':False,'different_physical_gpu_host':False}
maintenance=False;candidate_created=False;original={}
def interrupted(signum,frame):
    raise RuntimeError('QUALIFICATION_INTERRUPTED:'+str(signum))
signal.signal(signal.SIGTERM,interrupted)
signal.signal(signal.SIGINT,interrupted)

def mark(stage,**fields):
    report['stages'].append({'stage':stage,'at':time.time(),**fields})
    (out/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({'stage':stage,**fields}),flush=True)

def command(parts,timeout=120):
    return subprocess.check_output(parts,cwd=bundle,env=env,text=True,stderr=subprocess.STDOUT,timeout=timeout).strip()

def logged(stage,parts,timeout=1800):
    mark(stage)
    with (out/(stage+'.log')).open('x') as log:
        subprocess.run(parts,cwd=bundle,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=timeout)

def request(url,payload=None,timeout=10):
    raw=json.dumps(payload,separators=(',',':')).encode() if payload is not None else None
    req=urllib.request.Request(url,data=raw,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=timeout) as response:
        return response.status,response.read(),dict(response.headers)

def wait_qwen(base,seconds=1800,container=None):
    start=time.monotonic()
    while time.monotonic()-start<seconds:
        if container:
            state=json.loads(command(['docker','inspect',container]))[0]
            if state['RestartCount'] or state['State']['Status'] not in ('running','created'):
                raise RuntimeError('QWEN_BOOT_EXITED_OR_RESTARTED:'+container)
        try:
            if request(base+'/health')[0]==200:
                models=json.loads(request(base+'/v1/models')[1])
                if any(row['id']=='nanobaseAI' for row in models['data']):return round(time.monotonic()-start,3)
        except (OSError,ValueError,KeyError):pass
        time.sleep(10)
    raise RuntimeError('QWEN_BOOT_TIMEOUT')

def wake_ocr(base,name):
    artifact=Path(args.fragment_artifact).read_bytes();source=json.loads(artifact)
    assert source['api_pg_match'] is True and source['application_writes']==0
    measurement=source['fragments'][0]['data']['measurement']
    assert hashlib.sha256(base64.b64decode(measurement['crop_image_base64'],validate=True)).hexdigest()==measurement['crop_sha256']
    payload={'model':'paddleocr-vl-1.6','temperature':0,'max_tokens':256,
             'messages':[{'role':'user','content':[{'type':'text','text':'OCR:'},
              {'type':'image_url','image_url':{'url':'data:image/png;base64,'+measurement['crop_image_base64']}}]}]}
    start=time.monotonic();status,raw,headers=request(base+'/v1/chat/completions',payload,timeout=900)
    result=json.loads(raw);assert status==200 and result['choices'][0]['finish_reason']=='stop'
    assert result['choices'][0]['message']['content'].strip()
    (out/(name+'.json')).write_text(json.dumps({'artifact_sha256':hashlib.sha256(artifact).hexdigest(),
        'request_sha256':hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest(),
        'seconds':time.monotonic()-start,'response':result,'cold_start_seconds':headers.get('X-Cold-Start-Seconds')},indent=2))

def shared(stage,qwen_base,ocr_base,qwen_container,ocr_container):
    logged(stage,['python3',str(Path(args.verification_script).resolve()),args.visual_artifact,
        args.fragment_artifact,str(out/(stage+'.json')),'--pair-artifact',args.pair_artifact,
        '--qwen-base',qwen_base,'--ocr-base',ocr_base,'--qwen-container',qwen_container,'--ocr-container',ocr_container])

try:
    report['gpu_inventory']=command(['nvidia-smi','--query-gpu=index,name,memory.total,driver_version','--format=csv,noheader'])
    report['docker_version']=command(['docker','version','--format','{{.Server.Version}}'])
    manifest=json.loads((bundle/'gpu-release-manifest.json').read_text())
    assert manifest['kind']=='editor-gpu-offline'
    configured=json.loads((bundle/'compose.yaml').read_text())
    assert set(manifest.get('runtime_environment',{}))=={'qwen','ocr'},'RUNNER_ENVIRONMENT_MANIFEST_REQUIRED'
    for role,expected in manifest['runtime_environment'].items():
        assert configured['services'][role]['environment']==expected,'RUNNER_ENVIRONMENT_MANIFEST_MISMATCH:'+role
    for name,wanted in manifest['files'].items():
        path=(bundle/name).resolve();assert path.is_relative_to(bundle)
        with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==wanted,'PACKAGE_HASH_MISMATCH:'+name
    for role,value in manifest['images'].items():
        assert command(['docker','image','inspect','--format','{{.Id}}',value['tag']])==value['id'],'IMAGE_ID_MISMATCH:'+role
    for role,model in manifest['models'].items():
        repo=bundle/'hf-cache/hub'/('models--'+model['repository'].replace('/','--'))
        assert (repo/'refs/main').read_text()==model['revision'],'HF_CACHE_REF_NOT_EXACT:'+role
        assert (repo/'snapshots'/model['revision']/'config.json').is_file(),'HF_SNAPSHOT_CONFIG_MISSING:'+role
    report['package_manifest_sha256']=hashlib.sha256((bundle/'gpu-release-manifest.json').read_bytes()).hexdigest()
    mark('PACKAGE_VERIFIED',files=len(manifest['files']),models=manifest['models'])
    assert not command(['docker','ps','-aq','--filter','label=com.docker.compose.project='+project])
    assert not command(['docker','volume','ls','-q','--filter','label=com.docker.compose.project='+project])
    for port in (18001,18010):
        with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    names=[args.live_qwen,args.live_ocr,args.live_gateway]
    original={row['Name'].lstrip('/'):row for row in json.loads(command(['docker','inspect',*names]))}
    assert original[args.live_qwen]['State']['Running'] and original[args.live_gateway]['State']['Running']
    report['original_runners']={name:{'id':row['Id'],'image':row['Image'],'running':row['State']['Running']} for name,row in original.items()}
    idle=[]
    for _ in range(3):
        metrics=request('http://127.0.0.1:8001/metrics')[1].decode()
        def values(metric):return [float(line.rsplit(' ',1)[1]) for line in metrics.splitlines() if line.startswith(metric+'{')]
        running=values('vllm:num_requests_running');waiting=values('vllm:num_requests_waiting')
        assert running and waiting and sum(running+waiting)==0,'LIVE_MODEL_BUSY'
        gateway=json.loads(request('http://127.0.0.1:8010/gateway/status')[1])
        assert gateway.get('active_requests')==0,'LIVE_OCR_BUSY_OR_STATUS_UNKNOWN'
        idle.append({'at':time.time(),'running':running,'waiting':waiting,'generated_tokens':values('vllm:generation_tokens_total')})
        time.sleep(10)
    assert all(row['generated_tokens']==idle[0]['generated_tokens'] for row in idle),'LIVE_MODEL_USED_DURING_IDLE_CHECK'
    allowed=set()
    for name in (args.live_qwen,args.live_ocr):
        if original[name]['State']['Running']:
            allowed.update(int(line.strip()) for line in command(['docker','top',name,'-eo','pid']).splitlines()[1:])
    active={int(line.strip()) for line in command(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits']).splitlines() if line.strip().isdigit()}
    assert active<=allowed,'OTHER_GPU_WORKLOAD_PRESENT'
    mark('LIVE_MODELS_IDLE',samples=idle)
    maintenance=True
    logged('stop-live-models',['docker','stop',args.live_gateway,args.live_ocr,args.live_qwen])
    candidate_created=True
    logged('create-offline-ocr',compose+['create','--no-build','--pull','never','ocr'])
    logged('start-offline-models',compose+['up','-d','--no-build','--pull','never','qwen','gateway'])
    report['qwen_cold_ready_seconds']=wait_qwen('http://127.0.0.1:18001',container=project+'-qwen')
    mark('COLD_QWEN_READY',seconds=report['qwen_cold_ready_seconds'])
    # HTTP readiness alone does not exercise the packaged Docker health command.
    # A missing interpreter previously made that command fail independently of
    # model availability; require the actual packaged check to succeed as well.
    for _ in range(12):
        state=json.loads(command(['docker','inspect',project+'-qwen']))[0]
        if state['RestartCount'] or not state['State']['Running']:
            raise RuntimeError('COLD_QWEN_RESTARTED_DURING_HEALTH_CHECK')
        health=state['State'].get('Health',{})
        if health.get('Status')=='healthy':break
        time.sleep(5)
    else:raise RuntimeError('PACKAGED_QWEN_DOCKER_HEALTH_NOT_READY')
    mark('PACKAGED_DOCKER_HEALTH_PASSED',status=health['Status'])
    wake_ocr('http://127.0.0.1:18010','cold-ocr-real-request')
    checks=[]
    for role in ('qwen','ocr'):
        name=project+'-'+role;container=json.loads(command(['docker','inspect',name]))[0]
        assert container['Image']==manifest['images'][role]['id']
        actual_env=dict(value.split('=',1) for value in container['Config']['Env'] if '=' in value)
        expected_env=manifest['runtime_environment'][role]
        assert all(actual_env.get(key)==value for key,value in expected_env.items()),'RUNTIME_ENVIRONMENT_MISMATCH:'+role
        model_mount=next(m for m in container['Mounts'] if m['Destination']=='/root/.cache/huggingface')
        assert Path(model_mount['Source']).resolve()==(bundle/'hf-cache').resolve() and model_mount['RW'] is False
        networks=list(container['NetworkSettings']['Networks']);assert len(networks)==1
        assert json.loads(command(['docker','network','inspect',networks[0]]))[0]['Internal'] is True
        probe="import os,socket,json; assert os.environ.get('HF_HUB_OFFLINE')=='1'; s=socket.socket();s.settimeout(2);blocked=s.connect_ex(('1.1.1.1',443))!=0;print(json.dumps({'external_tcp_blocked':blocked}));assert blocked"
        blocked=json.loads(command(['docker','exec',name,'python3','-c',probe]))
        checks.append({'role':role,'image':container['Image'],'packaged_model_mount_read_only':True,
                       'runtime_environment':expected_env,**blocked})
    mark('OFFLINE_RUNTIME_BOUNDARIES',checks=checks)
    shared('cold-shared-inference','http://127.0.0.1:18001','http://127.0.0.1:18010',project+'-qwen',project+'-ocr')
    report['offline_boot_and_real_inference_passed']=True
except Exception as exc:
    report['failure']=type(exc).__name__+': '+str(exc)
    mark('FAILED',error=report['failure'])
finally:
    cleanup=[]
    if candidate_created:
        for service in ('qwen','ocr','gateway'):
            try:
                with (out/('offline-'+service+'.log')).open('w') as log:
                    subprocess.run(compose+['logs','--no-color',service],cwd=bundle,env=env,
                                   stdout=log,stderr=subprocess.STDOUT,timeout=60,check=True)
            except Exception as exc:
                cleanup.append('CANDIDATE_LOG_FAILED:'+service+':'+type(exc).__name__)
        try:
            logged('stop-offline-models',compose+['stop'])
            assert not command(compose+['ps','-q']),'OFFLINE_CONTAINERS_STILL_RUNNING'
        except Exception as exc:cleanup.append('CANDIDATE_STOP_FAILED:'+type(exc).__name__)
    if maintenance:
        try:
            for name in (args.live_qwen,args.live_ocr,args.live_gateway):
                current=json.loads(command(['docker','inspect',name]))[0]
                assert current['Id']==original[name]['Id'] and current['Image']==original[name]['Image'],'ORIGINAL_RUNNER_CHANGED'
            logged('restore-live-qwen',['docker','start',args.live_qwen])
            report['restored_qwen_ready_seconds']=wait_qwen('http://127.0.0.1:8001',1200)
            logged('restore-live-gateway',['docker','start',args.live_gateway])
            time.sleep(2)
            wake_ocr('http://127.0.0.1:8010','restored-ocr-real-request')
            shared('restored-shared-inference','http://127.0.0.1:8001','http://127.0.0.1:8010',args.live_qwen,args.live_ocr)
            report['live_runners_restored_and_inference_verified']=True
        except Exception as exc:cleanup.append('LIVE_RESTORE_FAILED:'+type(exc).__name__+': '+str(exc))
    report['cleanup_errors']=cleanup
    report['status']='PASS' if report.get('offline_boot_and_real_inference_passed') and report.get('live_runners_restored_and_inference_verified') and not cleanup else 'FAILED'
    report['finished_at']=time.time();mark('COMPLETE',status=report['status'])
raise SystemExit(0 if report['status']=='PASS' else 1)
