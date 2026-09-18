#!/usr/bin/env python3
"""Export the selected live GPU runners and pinned HF snapshots, without secrets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from runner_environment import capture_environment

p=argparse.ArgumentParser()
p.add_argument('destination')
p.add_argument('--cache',default='/data/hf-cache')
p.add_argument('--main-container',default='qwen38-flash-next')
p.add_argument('--ocr-container',default='paddleocr-vl')
p.add_argument('--gateway-container',default='paddleocr-gateway')
args=p.parse_args()
destination=Path(args.destination).resolve();cache=Path(args.cache).resolve()
assert not destination.exists(),'DESTINATION_ALREADY_EXISTS'
assert not destination.is_relative_to(cache),'DESTINATION_INSIDE_MODEL_CACHE'
names=[args.main_container,args.ocr_container,args.gateway_container]
containers=json.loads(subprocess.check_output(['docker','inspect',*names]))
roles=dict(zip(('qwen','ocr','gateway'),containers))
images={role:row['Image'] for role,row in roles.items()}
image_rows=json.loads(subprocess.check_output(['docker','image','inspect',*sorted(set(images.values()))]))
image_by_id={row['Id']:row for row in image_rows}
runtime_environment={role:capture_environment(roles[role],image_by_id[images[role]]) for role in ('qwen','ocr')}
models={};required_bytes=sum(row['Size'] for row in image_rows)
for role in ('qwen','ocr'):
    command=roles[role]['Config']['Cmd']
    assert command and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',command[0]),'EXPECTED_HF_REPOSITORY_COMMAND'
    assert not any(value.split('=',1)[0] in ('--api-key','--hf-token','--token') for value in command),'SECRET_BEARING_RUNNER_COMMAND'
    repository=command[0];repo=cache/'hub'/('models--'+repository.replace('/','--'))
    revision=(repo/'refs/main').read_text().strip()
    assert re.fullmatch(r'[0-9a-f]{40}',revision),'UNPINNED_HF_REVISION'
    snapshot=repo/'snapshots'/revision
    files=sorted(path for path in snapshot.rglob('*') if path.is_file())
    assert files and any(path.suffix=='.safetensors' for path in files),'MODEL_WEIGHTS_MISSING'
    for path in files:assert path.resolve().is_relative_to(repo.resolve()),'MODEL_CACHE_SYMLINK_ESCAPE'
    required_bytes+=sum(path.stat().st_size for path in files)
    models[role]={'repository':repository,'revision':revision,'snapshot':snapshot,'repo':repo,'files':files}
destination.parent.mkdir(parents=True,exist_ok=True)
assert shutil.disk_usage(destination.parent).free>required_bytes*1.25+10*1024**3,'INSUFFICIENT_PACKAGE_SPACE'
destination.mkdir()
manifest={'kind':'editor-gpu-offline','created_at':time.time(),'files':{},'models':{},
          'images':{},'qualification':'EXPORTED_CACHE_AND_RUNNER_IDENTITIES_NOT_FRESH_GPU_INSTALL_ACCEPTANCE',
          'secrets_included':False,'model_services_restarted':False}
manifest['runtime_environment']=runtime_environment
def copy_file(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    before=source.stat();digest=hashlib.sha256()
    with source.open('rb') as inp,target.open('xb') as out:
        while chunk:=inp.read(16*1024*1024):digest.update(chunk);out.write(chunk)
    after=source.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns),'SOURCE_CHANGED_DURING_EXPORT'
    manifest['files'][str(target.relative_to(destination))]=digest.hexdigest()
def write(relative,text):
    target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
    manifest['files'][relative]=hashlib.sha256(target.read_bytes()).hexdigest()
for role,model in models.items():
    repo_name=model['repo'].name
    manifest['models'][role]={'repository':model['repository'],'revision':model['revision'],'file_count':len(model['files'])}
    for index,path in enumerate(model['files'],1):
        relative=Path('hf-cache/hub')/repo_name/'snapshots'/model['revision']/path.relative_to(model['snapshot'])
        copy_file(path,destination/relative)
        if index%10==0:print(json.dumps({'stage':'model_files','role':role,'completed':index,'total':len(model['files'])}),flush=True)
    # HF reads a ref literally; a trailing newline becomes part of the directory
    # name and breaks offline snapshot resolution despite valid file hashes.
    write(str(Path('hf-cache/hub')/repo_name/'refs/main'),model['revision'])
tags={}
for role,identity in images.items():
    tag='nanobase-editor-gpu/image:'+identity.split(':')[1][:24]
    subprocess.run(['docker','image','tag',identity,tag],check=True)
    tags[role]=tag;manifest['images'][role]={'id':identity,'tag':tag}
services={}
for role in ('qwen','ocr'):
    live=roles[role];host=live['HostConfig'];command=list(live['Config']['Cmd'])
    gpu=host['DeviceRequests'];assert len(gpu)==1 and gpu[0]['DeviceIDs'],'EXPLICIT_GPU_DEVICES_REQUIRED'
    services[role]={'image':tags[role],'pull_policy':'never','restart':'unless-stopped' if role=='qwen' else 'no',
        'container_name':'${COMPOSE_PROJECT_NAME:-editor-gpu}-'+role,
        'command':command,'ipc':host['IpcMode'],
        'environment':runtime_environment[role],
        'volumes':['./hf-cache:/root/.cache/huggingface:ro',role+'_vllm_cache:/root/.cache/vllm'],
        'deploy':{'resources':{'reservations':{'devices':[{'driver':'nvidia','device_ids':gpu[0]['DeviceIDs'],'capabilities':['gpu']}]}}}}
    if host.get('CapAdd'):services[role]['cap_add']=host['CapAdd']
    if host.get('Ulimits'):services[role]['ulimits']={v['Name']:{'soft':v['Soft'],'hard':v['Hard']} for v in host['Ulimits']}
services['qwen']['ports']=['${GPU_BIND_ADDRESS:-127.0.0.1}:${QWEN_PORT:-8001}:8000']
services['qwen']['healthcheck']={'test':['CMD','python3','-c','import urllib.request;urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5)'],
    'interval':'15s','timeout':'8s','retries':80,'start_period':'180s'}
services['gateway']={'image':tags['gateway'],'pull_policy':'never','restart':'unless-stopped',
    'command':['python','/app/gateway.py'],'read_only':True,'cap_drop':['ALL'],
    'security_opt':['no-new-privileges:true'],'pids_limit':64,'mem_limit':'128m',
    'ports':['${GPU_BIND_ADDRESS:-127.0.0.1}:${OCR_PORT:-8010}:8080'],
    'environment':{'TARGET':'${COMPOSE_PROJECT_NAME:-editor-gpu}-ocr','UP_HOST':'ocr','UP_PORT':'8000',
                   'IDLE_SECONDS':'${OCR_IDLE_SECONDS:-600}','START_TIMEOUT':'600'},
    'volumes':['/var/run/docker.sock:/var/run/docker.sock']}
compose={'name':'${COMPOSE_PROJECT_NAME:-editor-gpu}','services':services,'volumes':{'qwen_vllm_cache':{},'ocr_vllm_cache':{}}}
write('compose.yaml',json.dumps(compose,indent=2)+'\n')
write('.env.example','COMPOSE_PROJECT_NAME=editor-gpu\nGPU_BIND_ADDRESS=127.0.0.1\nQWEN_PORT=8001\nOCR_PORT=8010\nOCR_IDLE_SECONDS=600\n')
copy_file(Path(__file__).with_name('import-bundle.py'),destination/'import-bundle.py')
copy_file(Path(__file__).with_name('runner_environment.py'),destination/'runner_environment.py')
copy_file(Path(__file__).with_name('INSTALL.md'),destination/'INSTALL.md')
print(json.dumps({'stage':'docker_image_export','images':len(set(tags.values()))}),flush=True)
subprocess.run(['docker','image','save','-o',str(destination/'images.tar'),*sorted(set(tags.values()))],check=True)
with (destination/'images.tar').open('rb') as stream:manifest['files']['images.tar']=hashlib.file_digest(stream,'sha256').hexdigest()
write('model-identities.json',json.dumps(manifest['models'],indent=2)+'\n')
(destination/'gpu-release-manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps({'destination':str(destination),'files':len(manifest['files']),'models':manifest['models'],
                  'qualification':manifest['qualification']}),flush=True)
