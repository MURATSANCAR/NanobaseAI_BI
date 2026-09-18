#!/usr/bin/env python3
"""Bounded concurrent inference on actual API/PG-verified book crops, on GPU host."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import urllib.request

p=argparse.ArgumentParser()
p.add_argument('visual_artifact');p.add_argument('fragment_artifact');p.add_argument('output')
p.add_argument('--pair-artifact',required=True)
args=p.parse_args();target=Path(args.output)
if target.exists():raise RuntimeError('EVIDENCE_ALREADY_EXISTS')
visual=json.loads(Path(args.visual_artifact).read_bytes())
fragment=json.loads(Path(args.fragment_artifact).read_bytes())
pair=json.loads(Path(args.pair_artifact).read_bytes())
for source in (visual,fragment,pair):
    assert source['api_pg_match'] is True and source['application_writes']==0
v=visual['result'];f=fragment['fragments'][0]['data']['measurement']
for proof in (v,f):
    assert hashlib.sha256(base64.b64decode(proof['crop_image_base64'],validate=True)).hexdigest()==proof['crop_sha256']
pair_data=pair['record']['data']
assert len(pair_data['crop_image_base64'])==len(pair_data['crop_sha256'])==2
for png,digest in zip(pair_data['crop_image_base64'],pair_data['crop_sha256']):
    assert hashlib.sha256(base64.b64decode(png,validate=True)).hexdigest()==digest
start_gate=threading.Barrier(3);done=threading.Event();samples=[]
def sample():
    while not done.is_set():
        raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,memory.free','--format=csv,noheader,nounits'],text=True)
        samples.append({'at':time.time(),'gpu_mib':[list(map(int,line.split(','))) for line in raw.splitlines()]})
        done.wait(.5)
def call(base,payload):
    raw=json.dumps(payload,separators=(',',':')).encode();started=time.time()
    request=urllib.request.Request(base+'/v1/chat/completions',data=raw,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=300) as response:answer=response.read();status=response.status
    result=json.loads(answer)
    assert status==200 and result['choices'][0]['finish_reason']=='stop'
    assert result['choices'][0]['message']['content'].strip()
    return {'started_at':started,'finished_at':time.time(),'request_sha256':hashlib.sha256(raw).hexdigest(),
            'response_sha256':hashlib.sha256(answer).hexdigest(),'response':result,'status':status}
def qwen(use_pair=False):
    start_gate.wait(timeout=30)
    prompt=('İki gerçek figür kırpımındaki görünür biçimlerin eşleşen ve farklı ayrıntılarını kaydet. İsim, yazı veya konuşmacı tahmin etme. JSON {"visible_details":["..."],"uncertainties":["..."]}.' if use_pair else
        'Bu gerçek figür kırpımında görünen biçim ve duruşu kaydet. Yazı okuma, isim veya konuşmacı tahmin etme. JSON {"visible_details":["..."],"uncertainties":["..."]}.')
    images=pair_data['crop_image_base64'] if use_pair else [v['crop_image_base64']]
    return call('http://127.0.0.1:8001',{'model':'qwen3.8-flash-next','temperature':0,'max_tokens':500,
        'chat_template_kwargs':{'enable_thinking':False},'response_format':{'type':'json_object'},
        'messages':[{'role':'user','content':[{'type':'text','text':prompt}]+
            [{'type':'image_url','image_url':{'url':'data:image/png;base64,'+png}} for png in images]}]})
def ocr():
    start_gate.wait(timeout=30);results=[]
    for _ in range(12):
        results.append(call('http://127.0.0.1:8010',{'model':'paddleocr-vl-1.6','temperature':0,'max_tokens':256,
            'messages':[{'role':'user','content':[{'type':'text','text':'OCR:'},
                {'type':'image_url','image_url':{'url':'data:image/png;base64,'+f['crop_image_base64']}}]}]}))
        time.sleep(.5)
    return results
sampler=threading.Thread(target=sample);sampler.start()
def runners():
    rows=json.loads(subprocess.check_output(['docker','inspect','qwen38-flash-next','paddleocr-vl']))
    return {r['Name']:{'container_id':r['Id'],'image_id':r['Image'],
                      'started_at':r['State']['StartedAt'],'command':r['Config']['Cmd']} for r in rows}
report={'environment':'GPU host / actual book crops verified against API and PostgreSQL',
        'visual_artifact_sha256':hashlib.sha256(Path(args.visual_artifact).read_bytes()).hexdigest(),
        'fragment_artifact_sha256':hashlib.sha256(Path(args.fragment_artifact).read_bytes()).hexdigest(),
        'pair_artifact_sha256':hashlib.sha256(Path(args.pair_artifact).read_bytes()).hexdigest(),
        'application_writes':0,'semantic_acceptance':False,'full_capacity_acceptance':False}
try:
    report['runners_before']=runners()
    with ThreadPoolExecutor(max_workers=3) as pool:
        a=pool.submit(qwen,True);b=pool.submit(qwen,False);c=pool.submit(ocr)
        report.update(qwen=[a.result(),b.result()],ocr=c.result())
    report['request_intervals_overlap']=all(any(max(q['started_at'],o['started_at'])<min(q['finished_at'],o['finished_at'])
                                                  for o in report['ocr']) for q in report['qwen'])
    assert report['request_intervals_overlap'],'CONCURRENT_INFERENCE_NOT_OBSERVED'
    report['runners_after']=runners()
    assert report['runners_before']==report['runners_after'],'RUNNER_RESTARTED_DURING_ACCEPTANCE'
    report['status']='PASS'
except Exception as exc:
    report.update(status='FAILED',error=type(exc).__name__+': '+str(exc))
    raise
finally:
    done.set();sampler.join();report['gpu_samples']=samples
    with target.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    target.chmod(0o600)
print(json.dumps({'status':report['status'],'qwen_requests':2,'ocr_requests':12,
    'request_intervals_overlap':report['request_intervals_overlap'],
    'minimum_free_mib':min(g[2] for s in samples for g in s['gpu_mib']),
    'semantic_acceptance':False,'full_capacity_acceptance':False}))
