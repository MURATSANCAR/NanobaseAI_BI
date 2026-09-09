"""Independent reference checks for multi-dimension production API answers."""
import os,sys,json,time,hashlib,urllib.request
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
os.environ['SEMANTIC_REFRESH_SEC']='0'
from enduser_10000 import corpus
from semantic_bridge.app import build_runtime
r=build_runtime();out=Path('/tmp/enduser-live-final-v4');out.mkdir(exist_ok=True)
wanted={'P01601','P01635','P03601','P03635','P05601','P05635','P07601','P07635','P09601','P09635','P09602','P09636'}
if os.environ.get('ENDUSER_EXTRA_SAMPLES')=='1':
 wanted={next(c['id'] for c in corpus() if c['year']==2026 and c['month']==1 and c['metric']==metric and c['level']==level and c['kind']==kind) for metric,level,kind in [('satış satırı sayısı',1,''),('satış satırı sayısı',5,''),('satılan adet',1,'perakende'),('satılan adet',5,'perakende')]}
 out=Path('/tmp/enduser-live-extra-final');out.mkdir(exist_ok=True)

cols,rows,tr=r.connector.execute("SELECT CAST(DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS VARCHAR(128)) AS collation",1)
collation=str(rows[0]['collation'])
assert (collation.lower().startswith('turkish') or 'cp1254_ci_' in collation.lower()) and '_ci_' in collation.lower(),collation
(out/'collation.json').write_text(json.dumps({'collation':collation,'comparison':'Turkish case-insensitive labels, numeric rounding 5 decimals'}))
def norm(rows):
 return sorted([tuple(sorted(('n',round(float(v),5)) if isinstance(v,(int,float,Decimal)) else ('s',str(v).strip().translate(str.maketrans({'I':'ı','İ':'i'})).lower()) for v in row)) for row in rows])
with (out/'results.jsonl').open('w') as f:
 for c in corpus():
  if c['id'] not in wanted:continue
  dims={'müşteri':'C.DEFINITION_','ürün':'I.NAME','ödeme planı':'P.DEFINITION_','satış temsilcisi':'R.DEFINITION_','teslimat şehri':'H.CITY','birim':'U.NAME'}
  joins=[]
  if c['level']>=2:joins+=['JOIN dbo.LG_411_ITEMS I ON S.STOCKREF=I.LOGICALREF']
  if c['level']>=3:joins+=['JOIN dbo.LG_411_01_INVOICE F ON S.INVOICEREF=F.LOGICALREF','LEFT JOIN dbo.LG_411_CLCARD C ON F.CLIENTREF=C.LOGICALREF']
  if c['level']>=4:joins+=['LEFT JOIN dbo.LG_411_PAYPLANS P ON COALESCE(NULLIF(S.PAYDEFREF,0),F.PAYDEFREF)=P.LOGICALREF','LEFT JOIN dbo.LG_SLSMAN R ON F.SALESMANREF=R.LOGICALREF']
  if c['level']==5:joins+=['LEFT JOIN dbo.LG_411_SHIPINFO H ON F.SHIPINFOREF=H.LOGICALREF']
  if 'birim' in c['dimensions']:joins+=['LEFT JOIN dbo.LG_411_UNITSETL U ON S.UOMREF=U.LOGICALREF']
  columns=', '.join(dims[d] for d in c['dimensions']);m=c['month']
  ref=f"SELECT {columns + ", " if columns else ""}SUM(S.AMOUNT) AS adet FROM dbo.LG_411_01_STLINE S {' '.join(joins)} WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.TRCODE IN (7,8) AND S.DATE_ >= '2026-{m:02d}-01' AND S.DATE_ < '2026-{m+1:02d}-01' {"GROUP BY " + columns if columns else ""}"
  if c['metric']=='satış satırı sayısı':ref=ref.replace('SUM(S.AMOUNT)','COUNT(S.LOGICALREF)')
  if c['kind']=='perakende':ref=ref.replace('S.TRCODE IN (7,8)','S.TRCODE = 7')
  # Independent business oracle: sold units exclude returns; combine the two
  # active firm catalogs without allowing references to cross firm boundaries.
  branches=[ref.replace('LG_411_',f'LG_{firm}_') for firm in ('211','411')]
  # Aggregate already grouped per-firm results again by the requested labels.
  aliases=[f'd{i}' for i in range(len(c['dimensions']))]
  branch_columns=', '.join(f'{dims[d]} AS {alias}' for d,alias in zip(c['dimensions'],aliases))
  branches=[b.replace('SELECT '+columns+', ', 'SELECT '+branch_columns+', ',1) if columns else b for b in branches]
  labels=', '.join(aliases)
  ref=f"SELECT {labels + ', ' if labels else ''}SUM(adet) AS adet FROM ({' UNION ALL '.join(branches)}) AS firms"+(f' GROUP BY {labels}' if labels else '')
  t=time.monotonic();item={'id':c['id'],'prompt':c['prompt'],'reference_sql':ref,'scope':'live production API; reference policy v3: sold units exclude returns; firms 211 and 411; effective line/header payment; invoice salesperson; nullable dimensions; complete row comparison'}
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
