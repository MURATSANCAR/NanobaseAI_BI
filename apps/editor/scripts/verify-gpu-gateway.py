#!/usr/bin/env python3
"""Run on the GPU host against a real book crop; never writes book records."""
import argparse
import base64
import hashlib
import http.client
import json
from pathlib import Path
import time
import urllib.request

p=argparse.ArgumentParser()
p.add_argument('fragment_artifact');p.add_argument('output')
p.add_argument('--port',type=int,default=8011)
p.add_argument('--model',default='paddleocr-vl-1.6')
args=p.parse_args()
artifact=Path(args.fragment_artifact).read_bytes();source=json.loads(artifact)
assert source['api_pg_match'] is True and source['application_writes']==0
fragment=source['fragments'][0]['data'];proof=fragment['measurement']
png=base64.b64decode(proof['crop_image_base64'],validate=True)
assert hashlib.sha256(png).hexdigest()==proof['crop_sha256']
base=f'http://127.0.0.1:{args.port}'
def status():
    with urllib.request.urlopen(base+'/gateway/status',timeout=45) as response:return json.load(response)
before=status();assert before['version']=='editor-ocr-gateway-v2'
rejections=[]
for length,expected in (('invalid',400),('-1',413),(str(32*1024*1024+1),413)):
    client=http.client.HTTPConnection('127.0.0.1',args.port,timeout=15)
    client.putrequest('POST','/v1/chat/completions')
    client.putheader('Content-Length',length);client.endheaders()
    response=client.getresponse();body=response.read();client.close()
    assert response.status==expected,(length,response.status)
    rejections.append({'length':length,'status':response.status,'response':json.loads(body)})
after_rejections=status()
assert after_rejections['starts']==before['starts'],'MALFORMED_REQUEST_WOKE_MODEL'
payload={'model':args.model,'messages':[{'role':'user','content':[
    {'type':'text','text':'OCR:'},
    {'type':'image_url','image_url':{'url':'data:image/png;base64,'+proof['crop_image_base64']}}]}],
    'temperature':0,'max_tokens':256}
request_bytes=json.dumps(payload,separators=(',',':')).encode()
request=urllib.request.Request(base+'/v1/chat/completions',data=request_bytes,headers={'Content-Type':'application/json'})
started=time.monotonic()
with urllib.request.urlopen(request,timeout=900) as response:raw=response.read();code=response.status
result=json.loads(raw)
assert code==200 and result['model']==args.model
assert result['choices'][0]['finish_reason']=='stop'
assert isinstance(result['choices'][0]['message']['content'],str) and result['choices'][0]['message']['content'].strip()
report={'gateway_version':before['version'],'environment':'remote GPU Docker / actual book crop',
    'source_artifact_sha256':hashlib.sha256(artifact).hexdigest(),'generation_id':source['generation_id'],
    'pdf_page':fragment['pdf_page'],'crop_sha256':proof['crop_sha256'],
    'request_sha256':hashlib.sha256(request_bytes).hexdigest(),'response_sha256':hashlib.sha256(raw).hexdigest(),
    'raw_response':raw.decode(),'seconds':round(time.monotonic()-started,3),
    'before':before,'after':status(),'malformed_requests':rejections,
    'real_inference_http_status':code,'application_writes':0,'semantic_acceptance':False,
    'idle_stop_start_race_verified':False}
target=Path(args.output)
with target.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
target.chmod(0o600)
print(json.dumps({k:v for k,v in report.items() if k not in ('raw_response','before','after')},ensure_ascii=False))
