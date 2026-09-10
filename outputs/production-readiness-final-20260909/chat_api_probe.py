import json,os,urllib.request,time,hashlib
from pathlib import Path
from decimal import Decimal
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def call(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8795'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
results=[]
for q in ['test','şişt','Sen kimsin?','asdfghjkl','Bana bir aşk şiiri yaz','Türkiye başkenti neresi?']:
 a=call('/api/v1/ask',{'question':q});row={'question':q,'type':a.get('type'),'passed':a.get('type')=='MODULE_INTRO' and not any(a.get(k) for k in ['sql','records','queryId','semantic'])};results.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
q='2026 toptan satış tutarı'
a=call('/api/v1/ask',{'question':q});print(json.dumps({'question':q,'type':a.get('type'),'sql':a.get('sql')},ensure_ascii=False),flush=True)
if a.get('resultId'):
 b=call('/api/v1/result/'+a['resultId']);s=SemanticSettings.from_env();c=connector_from_file(s.connection_file)
 reference="SELECT SUM(NETTOTAL) AS total FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE=8 AND DATE_ >= '20260101' AND DATE_ < '20270101'"
 expected=c.execute(reference,1)[1][0]['total'];c.close()
 values=list(b['records'][0].values()) if len(b['records'])==1 else []
 passed=len(values)==1 and abs(Decimal(str(values[0]))-Decimal(str(expected)))<Decimal('0.01') and not b.get('truncated')
 results.append({'question':q,'passed':passed,'type':a.get('type'),'actual':b,'referenceSQL':reference,'expected':str(expected)})
else:results.append({'question':q,'passed':False,'answer':a})
root=Path('/data/nanobaseai/bi/backups/zeki-chat-20260909')
(root/'acceptance.json').write_text(json.dumps({'results':results,'appSHA':hashlib.sha256(Path('/data/nanobaseai/bi/frontend/backend/semantic_bridge/app.py').read_bytes()).hexdigest()},ensure_ascii=False,indent=2,default=str))
print(json.dumps({'passed':sum(r['passed'] for r in results),'total':len(results)}),flush=True)
