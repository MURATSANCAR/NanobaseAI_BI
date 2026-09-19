#!/usr/bin/env python3
"""Measure a configured model route with an actual API/PG-verified figure pair."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import time
import urllib.request

p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('output');p.add_argument('--base-url',required=True)
args=p.parse_args();output=Path(args.output)
assert not output.exists(),'EVIDENCE_ALREADY_EXISTS'
raw=Path(args.source).read_bytes();source=json.loads(raw)
assert source['api_pg_match'] is True and source['application_writes']==0
pair=source['record']['data'];images=pair['crop_image_base64']
assert len(images)==len(pair['crop_sha256'])==2
for image,digest in zip(images,pair['crop_sha256']):
    assert hashlib.sha256(base64.b64decode(image,validate=True)).hexdigest()==digest
payload={'model':'nanobaseAI','temperature':0,'max_tokens':550,
    'chat_template_kwargs':{'enable_thinking':False},'response_format':{'type':'json_object'},
    'messages':[{'role':'user','content':[{'type':'text','text':'İki gerçek figür kırpımındaki görünür biçimleri karşılaştır. İsim, yazı, konuşmacı veya öykü tahmin etme. JSON {"matching_features":["..."],"conflicting_features":["..."],"uncertainties":["..."]}.'}]+
        [{'type':'image_url','image_url':{'url':'data:image/png;base64,'+image}} for image in images]}]}
encoded=json.dumps(payload,separators=(',',':')).encode();start=time.monotonic()
req=urllib.request.Request(args.base_url.rstrip('/')+'/v1/chat/completions',data=encoded,headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req,timeout=300) as response:result_raw=response.read();status=response.status
result=json.loads(result_raw);assert status==200 and result['choices'][0]['finish_reason']=='stop'
answer=json.loads(result['choices'][0]['message']['content']);assert isinstance(answer,dict)
report={'base_url':args.base_url,'seconds':round(time.monotonic()-start,3),'http_status':status,
    'source_artifact_sha256':hashlib.sha256(raw).hexdigest(),'record_id':source['record']['id'],
    'request_sha256':hashlib.sha256(encoded).hexdigest(),'request_bytes':len(encoded),
    'response_sha256':hashlib.sha256(result_raw).hexdigest(),'response':result,
    'application_writes':0,'semantic_acceptance':False}
with output.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
output.chmod(0o600)
print(json.dumps({k:v for k,v in report.items() if k!='response'}))
