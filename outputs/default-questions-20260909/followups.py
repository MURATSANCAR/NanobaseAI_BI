import json,os,urllib.request
from pathlib import Path
from decimal import Decimal
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
root=Path('/data/nanobaseai/bi/backups/default-questions-20260909');ref=json.loads((root/'reference-results.json').read_text())[0]['referenceSQL']
s=SemanticSettings.from_env();c=connector_from_file(s.connection_file)
headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def call(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8795'+path,data=json.dumps(body).encode() if body else None,headers=headers)
 with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
def norm(label,value):return (str(label) if label is not None else None,str(Decimal(str(value)).quantize(Decimal('0.00001'))))
a=call('/api/v1/ask',{'question':'2026 kanal bazında net ciro'});thread=a['threadId'];out=[]
for question,year,channel in [('2025',2025,None),('Peki 2024',2024,None),('sadece KITAPCI',2024,'KITAPCI')]:
 a=call('/api/v1/ask',{'question':question,'threadId':thread});row={'question':question,'answer':a,'status':'FAIL'}
 sql = "WITH entries AS (" + " UNION ALL ".join(
  f"SELECT c.SPECODE2 label,i.TRCODE,i.NETTOTAL FROM dbo.LG_{firm}_01_INVOICE i INNER JOIN dbo.LG_{firm}_CLCARD c ON c.LOGICALREF=i.CLIENTREF WHERE i.CANCELLED=0 AND i.DATE_ >= '{year}0101' AND i.DATE_ < '{year+1}0101' AND i.TRCODE IN (2,3,7,8,9)" for firm in ['211','411']) + ") SELECT label,SUM(CASE WHEN TRCODE IN (2,3) THEN -NETTOTAL ELSE NETTOTAL END) value FROM entries GROUP BY label"
 if channel:sql=sql.replace(' GROUP BY'," WHERE label='KITAPCI' GROUP BY")
 cols,rows,tr=c.execute(sql,100000);expected=sorted([norm(r['label'],r['value']) for r in rows],key=str)
 if a.get('resultId'):
  b=call('/api/v1/result/'+a['resultId']);row['fullResult']=b
  nums=[col['name'] for col in b['columns'] if col['type'] in ['float','int','Decimal']];labs=[col['name'] for col in b['columns'] if col['name'] not in nums]
  if len(nums)==len(labs)==1:
   actual=sorted([norm(r[labs[0]],r[nums[0]]) for r in b['records']],key=str)
   if actual==expected and not b['truncated'] and not tr:row['status']='LIVE_PASS'
 row['referenceSQL']=sql;row['expected']=expected;out.append(row);print(json.dumps({'question':question,'status':row['status'],'type':a.get('type')},ensure_ascii=False),flush=True)
(root/'followups.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));c.close()
