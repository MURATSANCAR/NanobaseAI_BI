#!/usr/bin/env python3
"""Observe natural idle shutdown, then wake OCR with an actual book crop."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

p=argparse.ArgumentParser()
p.add_argument('fragment_artifact');p.add_argument('output_directory')
p.add_argument('--port',type=int,default=8010)
p.add_argument('--max-wait',type=int,default=1200)
args=p.parse_args()
assert 1<=args.max_wait<=3600
out=Path(args.output_directory);out.mkdir(exist_ok=False)
def status():
    with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/gateway/status',timeout=45) as response:return json.load(response)
initial=status();assert initial['version']=='editor-ocr-gateway-v2'
deadline=time.monotonic()+args.max_wait
last=initial
while last['running']:
    if time.monotonic()>deadline:
        (out/'result.json').write_text(json.dumps({'status':'NOT_VERIFIED','reason':'NO_NATURAL_IDLE_WINDOW',
            'initial':initial,'last':last,'model_manually_stopped':False},indent=2))
        raise SystemExit('NO_NATURAL_IDLE_WINDOW')
    time.sleep(5);last=status()
assert last['active_requests']==0 and last['stops']>=1
(out/'naturally-stopped.json').write_text(json.dumps(last,indent=2))
subprocess.run([sys.executable,str(Path(__file__).with_name('verify-gpu-gateway.py')),
    args.fragment_artifact,str(out/'wake-inference.json'),'--port',str(args.port)],check=True)
inference=json.loads((out/'wake-inference.json').read_text())
assert inference['before']['running'] is False
after=inference['after']
assert after['running'] is True and after['healthy'] is True
assert after['starts']>inference['before']['starts']
result={'status':'PASS','natural_idle_shutdown':True,'real_crop_wake_inference':True,
    'model_manually_stopped':False,'gateway_version':initial['version'],
    'crop_sha256':inference['crop_sha256'],'real_inference_http_status':inference['real_inference_http_status'],
    'initial':initial,'naturally_stopped':last,'after':after,'application_writes':0,
    'semantic_acceptance':False,'adversarial_shutdown_request_race_verified':False}
(out/'result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
