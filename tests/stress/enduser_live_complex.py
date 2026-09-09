"""Independent reference checks for multi-dimension production API answers."""
import os,sys,json,time,hashlib,urllib.request
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
os.environ['SEMANTIC_REFRESH_SEC']='0'
from enduser_10000 import corpus
from semantic_bridge.app import build_runtime
r=build_runtime();out=Path('/tmp/enduser-live-complex-final');out.mkdir(exist_ok=True)
wanted={'P05601','P05635','P07601','P07635','P09601','P09635','P09602','P09636'}
def norm(rows):
 return sorted([tuple(sorted(('n',round(float(v),5)) if isinstance(v,(int,float,Decimal)) else ('s',str(v).strip()) for v in row)) for row in rows])
with (out/'results.jsonl').open('w') as f:
 for c in corpus():
  if c['id'] not in wanted:continue
  dims={'müşteri':'C.DEFINITION_','ürün':'I.NAME','ödeme planı':'P.DEFINITION_','satış temsilcisi':'R.DEFINITION_','teslimat şehri':'H.CITY','birim':'U.NAME'}
  joins=['JOIN dbo.LG_411_01_INVOICE F ON S.INVOICEREF=F.LOGICALREF','JOIN dbo.LG_411_ITEMS I ON S.STOCKREF=I.LOGICALREF','JOIN dbo.LG_411_CLCARD C ON F.CLIENTREF=C.LOGICALREF']
  if c['level']>=4:joins+=['JOIN dbo.LG_411_PAYPLANS P ON F.PAYDEFREF=P.LOGICALREF','JOIN dbo.LG_SLSMAN R ON F.SALESMANREF=R.LOGICALREF']
  if c['level']==5:joins+=['JOIN dbo.LG_411_SHIPINFO H ON F.SHIPINFOREF=H.LOGICALREF']
  if 'birim' in c['dimensions']:joins+=['JOIN dbo.LG_411_UNITSETL U ON S.UOMREF=U.LOGICALREF']
  columns=', '.join(dims[d] for d in c['dimensions']);m=c['month']
  ref=f"SELECT {columns}, SUM(CASE WHEN S.TRCODE IN (7,8) THEN S.AMOUNT ELSE 0 END) AS adet FROM dbo.LG_411_01_STLINE S {' '.join(joins)} WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.TRCODE IN (2,3,7,8) AND S.DATE_ >= '2026-{m:02d}-01' AND S.DATE_ < '2026-{m+1:02d}-01' GROUP BY {columns}"
  t=time.monotonic();item={'id':c['id'],'prompt':c['prompt'],'reference_sql':ref,'scope':'live production API; invoice-linked dimensions; complete row comparison'}
  try:
   cols,rows,truncated=r.connector.execute(ref,100000)
   truth=norm([[row.get(col['name']) for col in cols] for row in rows])
   req=urllib.request.Request('http://127.0.0.1:8795/api/v1/ask',data=json.dumps({'question':c['prompt'],'sampleSize':100000}).encode(),headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']})
   with urllib.request.urlopen(req,timeout=180) as resp:a=json.load(resp)
   actual=norm([list(row.values()) for row in a.get('records',[])])
   generated_truncated=False
   if a.get('type')=='TEXT_TO_SQL' and a.get('sql'):
    actual_cols,actual_rows,generated_truncated=r.connector.execute(r._physical(a['sql']),100000)
    actual=norm([[row.get(col['name']) for col in actual_cols] for row in actual_rows])
   ok=a.get('type')=='TEXT_TO_SQL' and not truncated and not generated_truncated and truth==actual
   status=('LIVE_PASS_SQL_PREVIEW_LIMITED' if a.get('truncated') else 'LIVE_PASS') if ok else 'LIVE_TRUNCATED' if truncated or generated_truncated else 'LIVE_FAIL' if a.get('type')=='TEXT_TO_SQL' else 'LIVE_'+str(a.get('type'))
   item.update(status=status,response_type=a.get('type'),sql=a.get('sql'),reason=a.get('explanation'),compiler=(a.get('semantic') or {}).get('compiler'),reference_rows=len(truth),answer_rows=len(actual),numeric_match=ok,preview_truncated=a.get('truncated'),preview_rows=len(a.get('records',[])),
     reference_sha256=hashlib.sha256(repr(truth).encode()).hexdigest(),answer_sha256=hashlib.sha256(repr(actual).encode()).hexdigest())
  except Exception as exc:item.update(status='LIVE_EXCEPTION',reason=str(exc)[:800])
  item['seconds']=round(time.monotonic()-t,1);f.write(json.dumps(item,ensure_ascii=False)+'\n');f.flush();print(json.dumps({k:v for k,v in item.items() if k not in ['reference_sql','sql']},ensure_ascii=False),flush=True)
if r.connector:r.connector.close()
