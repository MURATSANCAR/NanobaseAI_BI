"""Checkpointed real production HTTP execution. Never labels missing oracles as passes."""
import os,sys,json,time,hashlib,urllib.request,collections,signal
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
os.environ['SEMANTIC_REFRESH_SEC']='0'
from enduser_10000 import corpus
from semantic_bridge.app import build_runtime
r=build_runtime()
out=Path(os.environ.get('ENDUSER_LIVE_OUT','/data/nanobaseai/bi/backups/enduser-real-10000-20260909'))
out.mkdir(parents=True,exist_ok=True)
cols,rows,tr=r.connector.execute("SELECT CAST(DATABASEPROPERTYEX(DB_NAME(), 'Collation') AS VARCHAR(128)) AS collation",1)
collation=str(rows[0]['collation'])
assert (collation.lower().startswith('turkish') or 'cp1254_ci_' in collation.lower()) and '_ci_' in collation.lower(),collation
(out/'collation.json').write_text(json.dumps({'collation':collation,'comparison':'Turkish case-insensitive labels, numeric rounding 5 decimals'}))
def norm(rows):
 return sorted([tuple(sorted(('n',round(float(v),5)) if isinstance(v,(int,float,Decimal)) else ('s',str(v).strip().translate(str.maketrans({'I':'ı','İ':'i'})).lower()) for v in row)) for row in rows])
def reference(c):
  if c['metric'] in ('satış tutarı','net satış tutarı') and c['level']==1:
   assert c['level']==1, 'Header amount requires an independently established allocation rule for product dimensions'
   net=c['metric']=='net satış tutarı'
   codes={'': '2,3,7,8,9' if net else '7,8,9','toptan':'3,8' if net else '8','perakende':'2,7' if net else '7'}[c['kind']]
   formula='SUM(CASE WHEN F.TRCODE IN (2,3) THEN -F.NETTOTAL ELSE F.NETTOTAL END)' if net else 'SUM(F.NETTOTAL)'
   y,m=c['year'],c['month']
   branches=[f"SELECT {formula} AS amount FROM dbo.LG_{firm}_01_INVOICE F WHERE F.CANCELLED=0 AND F.TRCODE IN ({codes}) AND F.DATE_ >= '{y}-{m:02d}-01' AND F.DATE_ < '{y+(m==12)}-{m%12+1:02d}-01'" for firm in ('211','411')]
   return 'SELECT SUM(amount) AS amount FROM ('+' UNION ALL '.join(branches)+') AS firms'
  dims={'müşteri':'C.DEFINITION_','ürün':'I.NAME','ödeme planı':'P.DEFINITION_','satış temsilcisi':'R.DEFINITION_','teslimat şehri':'H.CITY','birim':'U.NAME'}
  joins=[]
  if c['level']>=2:joins+=['JOIN dbo.LG_411_ITEMS I ON S.STOCKREF=I.LOGICALREF']
  if c['level']>=3:joins+=['JOIN dbo.LG_411_01_INVOICE F ON S.INVOICEREF=F.LOGICALREF','LEFT JOIN dbo.LG_411_CLCARD C ON F.CLIENTREF=C.LOGICALREF']
  if c['level']>=4:joins+=['LEFT JOIN dbo.LG_411_PAYPLANS P ON COALESCE(NULLIF(S.PAYDEFREF,0),F.PAYDEFREF)=P.LOGICALREF','LEFT JOIN dbo.LG_SLSMAN R ON F.SALESMANREF=R.LOGICALREF']
  if c['level']==5:joins+=['LEFT JOIN dbo.LG_411_SHIPINFO H ON F.SHIPINFOREF=H.LOGICALREF']
  if 'birim' in c['dimensions']:joins+=['LEFT JOIN dbo.LG_411_UNITSETL U ON S.UOMREF=U.LOGICALREF']
  columns=', '.join(dims[d] for d in c['dimensions']);m=c['month']
  ref=f"""SELECT {columns + ", " if columns else ""}SUM(S.AMOUNT) AS adet FROM dbo.LG_411_01_STLINE S {' '.join(joins)} WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.TRCODE IN (7,8) AND S.DATE_ >= '{c['year']}-{m:02d}-01' AND S.DATE_ < '{c['year'] + (m == 12)}-{m % 12 + 1:02d}-01' {"GROUP BY " + columns if columns else ""}"""
  if c['metric']=='satış tutarı':ref=ref.replace('SUM(S.AMOUNT)','SUM(S.LINENET)')
  if c['metric']=='net satış tutarı':
   ref=ref.replace('SUM(S.AMOUNT)','SUM(CASE WHEN S.TRCODE IN (2,3) THEN -S.LINENET ELSE S.LINENET END)').replace('S.TRCODE IN (7,8)','S.TRCODE IN (2,3,7,8)')
   if c['kind']:ref=ref.replace('S.TRCODE IN (2,3,7,8)', 'S.TRCODE IN (2,7)' if c['kind']=='perakende' else 'S.TRCODE IN (3,8)')
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
  ref=f"""SELECT {labels + ', ' if labels else ''}SUM(adet) AS adet FROM ({' UNION ALL '.join(branches)}) AS firms"""+(f' GROUP BY {labels}' if labels else '')
  if c['kind']=='toptan':ref=ref.replace('S.TRCODE IN (7,8)','S.TRCODE = 8')
  return ref

stop_requested=False
def request_stop(*args):
 global stop_requested
 stop_requested=True
signal.signal(signal.SIGTERM,request_stop)
signal.signal(signal.SIGINT,request_stop)
done={}
if (out/'results.jsonl').exists():
 for line in (out/'results.jsonl').read_text().splitlines():
  item=json.loads(line);done[item['id']]=item
cases=corpus()
selected_ids=set(filter(None,os.environ.get("ENDUSER_IDS","").split(",")))
if selected_ids:cases=[c for c in cases if c["id"] in selected_ids]
# First traverse simple to complex using current-data quantity cases, then all remaining IDs.
priority=[]
for level in range(1,6):
 priority.extend([c for c in cases if c['level']==level and c['year']==2026 and c['month'] in (1,2) and c['metric']=='satılan adet' and not c['kind']][:2])
ids={c['id'] for c in priority}
cases=priority+[c for c in cases if c['id'] not in ids]
(out/'manifest.json').write_text(json.dumps({'count':len(cases),'ids':[c['id'] for c in cases],'scope':'Actual production HTTP for every prompt; full SQL/reference comparison where independently defined; others explicitly unverified'},ensure_ascii=False))
with (out/'results.jsonl').open('a') as f:
 for c in cases:
  if c['id'] in done:continue
  if stop_requested or (out/'STOP').exists():break
  t=time.monotonic();item={'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'id':c['id'],'prompt':c['prompt'],'metric':c['metric'],'level':c['level'],'scope':'actual production API and connected database'}
  try:
   req=urllib.request.Request('http://127.0.0.1:8795/api/v1/ask',data=json.dumps({'question':c['prompt'],'sampleSize':100000}).encode(),headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']})
   with urllib.request.urlopen(req,timeout=180) as resp:a=json.load(resp)
   (out/(c['id']+'.json')).write_text(json.dumps(a,ensure_ascii=False,default=str))
   item.update(response_type=a.get('type'),sql=a.get('sql'),reason=a.get('explanation'),compiler=(a.get('semantic') or {}).get('compiler'),preview_rows=len(a.get('records',[])),preview_truncated=a.get('truncated'))
   item['status']='LIVE_RESPONSE_UNVERIFIED'
   if a.get('type')=='TEXT_TO_SQL' and a.get('sql'):
    item['status']='LIVE_SQL_UNVERIFIED'
    if c['metric'] in ('satılan adet','satış satırı sayısı','satış tutarı','net satış tutarı'):
     ref=reference(c)
     cols,rows,tr=r.connector.execute(ref,100000)
     truth=norm([[row.get(col['name']) for col in cols] for row in rows])
     ac,ar,at=r.connector.execute(r._physical(a['sql']),100000)
     actual=norm([[row.get(col['name']) for col in ac] for row in ar])
     ok=not tr and not at and truth==actual
     item.update(reference_sql=ref,reference_rows=len(truth),answer_rows=len(actual),numeric_match=ok,status=('LIVE_PASS_SQL_PREVIEW_LIMITED' if a.get('truncated') else 'LIVE_PASS') if ok else 'LIVE_TRUNCATED' if tr or at else 'LIVE_FAIL',reference_sha256=hashlib.sha256(repr(truth).encode()).hexdigest(),answer_sha256=hashlib.sha256(repr(actual).encode()).hexdigest())
  except Exception as exc:item.update(status='LIVE_EXCEPTION',reason=str(exc)[:800])
  item['seconds']=round(time.monotonic()-t,2)
  f.write(json.dumps(item,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno());done[c['id']]=item
  counts=dict(collections.Counter(x['status'] for x in done.values()))
  progress={'completed':len(done),'total':len(cases),'counts':counts,'last_id':c['id']}
  (out/'progress.json').write_text(json.dumps(progress,ensure_ascii=False))
  print(json.dumps(progress,ensure_ascii=False),flush=True)
if r.connector:r.connector.close()
