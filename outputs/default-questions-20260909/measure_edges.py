import json,os,urllib.request
from pathlib import Path
from decimal import Decimal
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
root=Path('/data/nanobaseai/bi/backups/default-questions-20260909');s=SemanticSettings.from_env();c=connector_from_file(s.connection_file)
headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def call(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8795'+path,data=json.dumps(body).encode() if body else None,headers=headers)
 with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
base="WITH lines AS ("+" UNION ALL ".join(f"SELECT AMOUNT,TRCODE FROM dbo.LG_{firm}_01_STLINE WHERE DATE_ >= '20260101' AND DATE_ < '20270101' AND CANCELLED=0 AND LINETYPE=0 AND TRCODE IN (2,3,7,8)" for firm in ['211','411'])+") "
qty=base+"SELECT SUM(CASE WHEN TRCODE IN (2,3) THEN AMOUNT ELSE 0 END) value FROM lines"
ratio=base+"SELECT SUM(CASE WHEN TRCODE IN (2,3) THEN AMOUNT ELSE 0 END) / NULLIF(SUM(CASE WHEN TRCODE IN (7,8) THEN AMOUNT ELSE 0 END),0) value FROM lines"
sales="WITH sales AS ("+" UNION ALL ".join(f"SELECT p.NAME label,l.LINENET value FROM dbo.LG_{firm}_01_STLINE l JOIN dbo.LG_{firm}_ITEMS p ON p.LOGICALREF=l.STOCKREF WHERE l.DATE_ >= '20260101' AND l.DATE_ < '20270101' AND l.CANCELLED=0 AND l.LINETYPE=0 AND l.TRCODE IN (7,8)" for firm in ['211','411'])+") SELECT TOP 10 label,SUM(value) value FROM sales GROUP BY label ORDER BY value DESC"
cases=[('2026 iade adedi',qty),('2026 iade adet',qty),('2026 iade oranı',ratio),('2026 kitap bazında satış tutarı ilk 10',sales)]
def norm(v):return str(Decimal(str(v)).quantize(Decimal('0.00001'))) if v is not None else None
out=[]
for q,sql in cases:
 a=call('/api/v1/ask',{'question':q});row={'question':q,'answer':a,'status':'FAIL','referenceSQL':sql}
 _,expected,tr=c.execute(sql,100000);row['reference']=expected
 if a.get('resultId'):
  b=call('/api/v1/result/'+a['resultId']);row['fullResult']=b
  nums=[col['name'] for col in b['columns'] if col['type'] in ['int','float','Decimal']];labs=[col['name'] for col in b['columns'] if col['name'] not in nums]
  if len(nums)==1 and len(labs)==(1 if sql==sales else 0):
   actual=sorted([(r[labs[0]] if labs else None,norm(r[nums[0]])) for r in b['records']],key=str)
   reference=sorted([(r.get('label'),norm(r['value'])) for r in expected],key=str)
   if actual==reference and not tr and not b['truncated']:row['status']='LIVE_PASS'
 out.append(row);print(json.dumps({'q':q,'status':row['status'],'type':a.get('type'),'explanation':a.get('explanation')},ensure_ascii=False),flush=True)
(root/'measure-edges.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str));c.close()
