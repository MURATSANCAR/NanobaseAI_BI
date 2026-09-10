import json,os,time,urllib.request
from pathlib import Path
root=Path('/data/nanobaseai/bi/backups/language-pool-20260909')
headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
qs=[('S01','999999 firmasında iade adedi'),('S02','211 ve 411 firmaları için iade adedi'),('S03','411 firması hariç iade adedi')]
rows=[]
for ident,q in qs:
 start=time.monotonic()
 request=urllib.request.Request('http://127.0.0.1:8795/api/v1/ask',data=json.dumps({'question':q}).encode(),headers=headers)
 with urllib.request.urlopen(request,timeout=60) as r:a=json.load(r)
 row={'id':ident,'question':q,'status':'GUARD_PASS' if a.get('type')=='CLARIFICATION' and not a.get('resultId') and not a.get('sql') else 'GUARD_FAIL','answer':a,'seconds':round(time.monotonic()-start,2)}
 rows.append(row);print(json.dumps({'id':ident,'status':row['status']},ensure_ascii=False),flush=True)
(root/'context-guards.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
