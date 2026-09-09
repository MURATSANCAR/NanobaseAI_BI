import json, os, time, urllib.request
from pathlib import Path
from decimal import Decimal
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
root=Path('/data/nanobaseai/bi/backups/language-pool-20260909')
s=SemanticSettings.from_env(); connector=connector_from_file(s.connection_file)
headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def call(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8795'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 with urllib.request.urlopen(req,timeout=240) as r:return json.load(r)
cases=[
 ('L01','411 firmasında aktif malzeme kartlarının sayısı nedir?', 'SELECT COUNT(*) AS value FROM dbo.LG_411_ITEMS WHERE ACTIVE=0'),
 ('L02',"411 firmasında kampanya puanı 10 üzerinde olan malzeme kartlarının sayısı nedir?", 'SELECT COUNT(*) AS value FROM dbo.LG_411_ITEMS WHERE CAMPPOINT>10'),
 ('L03','411 firmasında kullanım dışı cari hesap kartlarının sayısı nedir?', 'SELECT COUNT(*) AS value FROM dbo.LG_411_CLCARD WHERE ACTIVE=1'),
 ('L04','411 firmasında e-mağaza kodu NULL veya boş metin olmayan malzeme kartlarının sayısı nedir?', "SELECT COUNT(*) AS value FROM dbo.LG_411_ITEMS WHERE B2CCODE IS NOT NULL AND B2CCODE<>''"),
]
base="WITH lines AS ("+" UNION ALL ".join(f"SELECT AMOUNT,TRCODE FROM dbo.LG_{firm}_01_STLINE WHERE DATE_ >= '20260101' AND DATE_ < '20270101' AND CANCELLED=0 AND LINETYPE=0 AND TRCODE IN (2,3,7,8)" for firm in ['211','411'])+") "
qty=base+"SELECT SUM(CASE WHEN TRCODE IN (2,3) THEN AMOUNT ELSE 0 END) value FROM lines"
ratio=base+"SELECT SUM(CASE WHEN TRCODE IN (2,3) THEN AMOUNT ELSE 0 END) / NULLIF(SUM(CASE WHEN TRCODE IN (7,8) THEN AMOUNT ELSE 0 END),0) value FROM lines"
cases.extend([('L05','2026 iade adedi',qty),('L06','2026 iade adet',qty),('L07','2026 iade oranı',ratio)])
sales="WITH sales AS ("+" UNION ALL ".join(f"SELECT p.NAME label,l.LINENET value FROM dbo.LG_{firm}_01_STLINE l JOIN dbo.LG_{firm}_ITEMS p ON p.LOGICALREF=l.STOCKREF WHERE l.DATE_ >= '20260101' AND l.DATE_ < '20270101' AND l.CANCELLED=0 AND l.LINETYPE=0 AND l.TRCODE IN (7,8)" for firm in ['211','411'])+") SELECT TOP 10 label,SUM(value) value FROM sales GROUP BY label ORDER BY value DESC"
cases.extend([('L08','2026 kitap bazında satış tutarı ilk 10',sales),('L09','2026 iade alan müşterilerin sayısı',None),('L10','2026 iptal edilen satışların tutarı',None)])
def number(v):return str(Decimal(str(v)).quantize(Decimal('0.00001'))) if v is not None else None
out=[]
for ident,q,ref in cases:
 row={'id':ident,'question':q,'referenceSQL':ref,'status':'DOĞRULANAMADI'};t=time.monotonic()
 try:
  answer=call('/api/v1/ask',{'question':q,'sampleSize':100000});row['answer']=answer
  query=(answer.get('semantic') or {}).get('query') or {};row['poolHash']=query.get('languagePoolHash');row['languageHits']=len(query.get('languageCandidates') or [])
  if ref:
   columns,expected,truncated=connector.execute(ref,100000);row['reference']=expected
   if answer.get('resultId'):
    full=call('/api/v1/result/'+answer['resultId']);row['fullResult']=full
    nums=[c['name'] for c in full['columns'] if c['type'] in ['int','float','Decimal']];labels=[c['name'] for c in full['columns'] if c['name'] not in nums]
    shape=len(nums)==1 and len(labels)==(1 if ident=='L08' else 0) and all(set(r)=={c['name'] for c in full['columns']} for r in full['records'])
    if shape:
     actual=sorted([(r[labels[0]] if labels else None,number(r[nums[0]])) for r in full['records']],key=str)
     truth=sorted([(r.get('label'),number(r['value'])) for r in expected],key=str)
     row['status']='LIVE_PASS' if actual==truth and not truncated and not full['truncated'] and len(actual)==full['totalRows'] else 'LIVE_FAIL'
    else:row['status']='LIVE_FAIL_COLUMN_CONTRACT'
   else:row['status']='NO_NUMERIC_ANSWER'
  else:
   row['status']='GUARD_PASS' if answer.get('type') in ['CLARIFICATION','INCOMPLETE_ANSWER'] and not answer.get('resultId') else 'GUARD_FAIL'
 except Exception as e:row['error']=str(e)[:500]
 row['seconds']=round(time.monotonic()-t,2);out.append(row)
 (root/'feature-acceptance.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
 print(json.dumps({k:row.get(k) for k in ['id','question','status','languageHits','seconds','error']},ensure_ascii=False),flush=True)
connector.close()
