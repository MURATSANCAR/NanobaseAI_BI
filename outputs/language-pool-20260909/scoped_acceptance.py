import json,os,sys,time,urllib.request,hashlib
from pathlib import Path
from decimal import Decimal
import sqlglot
from sqlglot import exp
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
sys.path.insert(0,'/data/nanobaseai/bi/frontend/tests/stress')
from enduser_10000 import corpus
from result_comparison import norm,aligned_rows
root=Path('/data/nanobaseai/bi/backups/language-pool-20260909')
c=connector_from_file(SemanticSettings.from_env().connection_file)
def call(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8795'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']})
 with urllib.request.urlopen(req,timeout=240) as resp:return json.load(resp)
case=next(x for x in corpus() if x['id']=='P09602')
assert case['metric']=='satılan adet' and case['year']==2026 and case['month']==1 and not case['kind'],case
exprs={'müşteri':'C.DEFINITION_','ürün':'I.NAME','ödeme planı':'P.DEFINITION_','satış temsilcisi':'R.DEFINITION_','teslimat şehri':'H.CITY','birim':'U.NAME'}
dims=','.join(exprs[x] for x in case['dimensions'])
select_dims=','.join(f'{exprs[x]} AS d{i}' for i,x in enumerate(case['dimensions']))
ref8=f'''SELECT {select_dims},SUM(S.AMOUNT) AS adet FROM dbo.LG_411_01_STLINE S
JOIN dbo.LG_411_ITEMS I ON S.STOCKREF=I.LOGICALREF
JOIN dbo.LG_411_01_INVOICE F ON S.INVOICEREF=F.LOGICALREF
LEFT JOIN dbo.LG_411_CLCARD C ON F.CLIENTREF=C.LOGICALREF
LEFT JOIN dbo.LG_411_PAYPLANS P ON COALESCE(NULLIF(S.PAYDEFREF,0),F.PAYDEFREF)=P.LOGICALREF
LEFT JOIN dbo.LG_SLSMAN R ON F.SALESMANREF=R.LOGICALREF
LEFT JOIN dbo.LG_411_SHIPINFO H ON F.SHIPINFOREF=H.LOGICALREF
LEFT JOIN dbo.LG_411_UNITSETL U ON S.UOMREF=U.LOGICALREF
WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.TRCODE IN(7,8)
AND S.DATE_ >= '2026-01-01' AND S.DATE_ < '2026-02-01' GROUP BY {dims}'''
refcmp="""SELECT SUM(CASE WHEN DATE_ >= '2026-09-01' AND DATE_ < '2026-10-01' THEN NETTOTAL END) AS current_value,SUM(CASE WHEN DATE_ >= '2026-08-01' AND DATE_ < '2026-09-01' THEN NETTOTAL END) AS previous_value FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE IN(7,8,9) AND DATE_ >= '2026-08-01' AND DATE_ < '2026-10-01'"""
cases=[('S04','411 firmasında 2026 iade adedi',"SELECT SUM(AMOUNT) AS value FROM dbo.LG_411_01_STLINE WHERE CANCELLED=0 AND LINETYPE=0 AND TRCODE IN(2,3) AND DATE_ >= '2026-01-01' AND DATE_ < '2027-01-01'",'scalar'),('S05','411 firmasında '+case['prompt'],ref8,'eight'),('S06','411 firmasında geçen aya göre satış tutarı',refcmp,'comparison')]
refyear="SELECT SUM(CASE WHEN DATE_ >= '2026-01-01' AND DATE_ < '2027-01-01' AND TRCODE IN(7,8,9) THEN NETTOTAL ELSE 0 END) AS current_value,SUM(CASE WHEN DATE_ >= '2025-01-01' AND DATE_ < '2026-01-01' AND TRCODE IN(7,8,9) THEN NETTOTAL ELSE 0 END) AS previous_value FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE IN(2,3,7,8,9) AND DATE_ >= '2025-01-01' AND DATE_ < '2027-01-01'"
cases.append(('S07','411 firmasında 2025 ve 2026 satış tutarı karşılaştırması',refyear,'year'))
rows=[]
for ident,q,ref,kind in cases:
 t=time.monotonic();row={'id':ident,'question':q,'referenceSQL':ref,'status':'DOĞRULANAMADI'}
 try:
  a=call('/api/v1/ask',{'question':q,'sampleSize':100000});row['answer']=a
  cols,truth,tr=c.execute(ref,100000)
  if a.get('resultId'):
   full=call('/api/v1/result/'+a['resultId']);row['fullResult']=full
   if kind=='eight':actual=aligned_rows(full,case)
   elif kind=='scalar':
    assert len(full['columns'])==1,'Scalar column contract'
    actual=[[r[full['columns'][0]['name']]] for r in full['records']]
   else:
    tree=sqlglot.parse_one(a['sql'],read='tsql');mapping={}
    for e in tree.expressions:
     dates={l.this for l in e.find_all(exp.Literal) if l.is_string}
     if ({'2026-01-01','2027-01-01'} if kind=='year' else {'2026-09-01','2026-10-01'})<=dates:mapping['current']=e.alias_or_name
     elif ({'2025-01-01','2026-01-01'} if kind=='year' else {'2026-08-01','2026-09-01'})<=dates:mapping['previous']=e.alias_or_name
    assert len(mapping)==2 and len(full['columns'])==2,('Comparison period column contract',mapping)
    actual=[[r[mapping['current']],r[mapping['previous']]] for r in full['records']]
   expected=[[r[x['name']] for x in cols] for r in truth]
   actual=norm(actual);expected=norm(expected)
   row.update(referenceRows=len(expected),answerRows=len(actual),referenceHash=hashlib.sha256(repr(expected).encode()).hexdigest(),answerHash=hashlib.sha256(repr(actual).encode()).hexdigest())
   scope=(a.get('semantic') or {}).get('query',{}).get('contextScope')
   assert scope=={'n0':'411'},('Scope not bound',scope)
   row['status']='LIVE_PASS' if actual==expected and not tr and not full['truncated'] and full['totalRows']==len(actual) else 'LIVE_FAIL'
  else:
   row['status']='GUARD_PASS' if ident=='S06' and a.get('type')=='DATA_UNAVAILABLE' and not tr and len(truth)==1 and truth[0]['current_value'] is None else 'NO_NUMERIC_ANSWER'
 except Exception as e:row['error']=str(e)[:500]
 row['seconds']=round(time.monotonic()-t,2);rows.append(row)
 (root/'scoped-acceptance-final.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=str))
 print(json.dumps({k:row.get(k) for k in ['id','status','referenceRows','answerRows','seconds','error']},ensure_ascii=False),flush=True)
c.close()
