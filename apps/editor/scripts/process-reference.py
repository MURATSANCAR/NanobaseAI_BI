#!/usr/bin/env python3
"""Run the real retained book through the same API an editor client would call."""
import json
from pathlib import Path
import urllib.request

root=Path(__file__).resolve().parents[1]
token=(root/'secrets/api_token').read_text().strip()
base='http://127.0.0.1:8810'


def post(path,body,key):
    request=urllib.request.Request(base+path,data=json.dumps(body).encode(),
      headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':'reference-v1-'+key})
    with urllib.request.urlopen(request,timeout=60) as response: return json.load(response)


work=post('/v1/works',{'title':'Ekrana Sığmayan Macera'},'work')
edition=post('/v1/editions',{'work_id':work['id'],'label':'Kullanıcının sağladığı iç baskı PDF'},'edition')
source=post('/v1/editions/'+edition['id']+'/verified-sources',
  {'sha256':'94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50'},'source')
job=post('/v1/content-versions/'+source['id']+'/analyses',{'purpose':'validation'},'analysis-page-local-tsv-v3')
result={'work':work,'edition':edition,'source':source,'job':job}
(root/'evidence/reference-book-run.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
