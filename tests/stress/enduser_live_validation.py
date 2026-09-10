"""Production-catalog readiness for all questions, plus independent live SQL checks.

Readiness is not execution success. Runtime HTTP samples are recorded separately.
"""
import os,sys,json,time,collections,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
os.environ['SEMANTIC_REFRESH_SEC']='0'
from enduser_10000 import corpus
from semantic_bridge.app import build_runtime
from semantic_layer.runtime.compiler import DeterministicCompiler,default_filters_provider
r=build_runtime();out=Path(os.environ.get('ENDUSER_READINESS_OUT','/tmp/enduser-production'));out.mkdir(exist_ok=True)
cases=corpus()[int(os.environ.get('ENDUSER_START','0')):int(os.environ.get('ENDUSER_END','10000'))];counts=collections.Counter();started=time.monotonic()
det=DeterministicCompiler(r.profiles,r.settings.context,r.settings.dialect,
    default_filters=default_filters_provider(r.store,r.settings.tenant_id,r.settings.datasource_id),conventions=r.conventions)
with (out/'readiness.jsonl').open('w') as f:
 for i,c in enumerate(cases):
  sq=r.resolver.resolve(c['prompt']);plan,reason=det.plan(sq)
  status='DETERMINISTIC_PLAN_READY' if plan else 'DATA_UNAVAILABLE' if sq.out_of_scope else 'NEEDS_CLARIFICATION' if sq.clarification else 'MODEL_REQUIRED'
  row={'id':c['id'],'status':status,'reason':reason,'unresolved':sq.unresolved,'clarification':sq.clarification,'actual_entities':sorted({s.mapping.entity for s in sq.slots if s.mapping}),'scope':'production catalog planning only; SQL not executed'}
  f.write(json.dumps(row,ensure_ascii=False)+'\n');counts[status]+=1
  if (i+1)%1000==0:print(json.dumps({'planned':i+1,'counts':dict(counts),'seconds':round(time.monotonic()-started,1)}),flush=True)
(out/'readiness-summary.json').write_text(json.dumps(dict(counts)))
if os.environ.get('ENDUSER_PLANNING_ONLY')=='1':
 if r.connector:r.connector.close()
 sys.exit(0)
# January/February 2026, same question text as the delivered corpus, one of each level.
selected=[]
for level in range(1,6):
 for month in (1,2):
  selected.append(next(c for c in cases if c['level']==level and c['year']==2026 and c['month']==month and c['metric']=='satılan adet' and not c['kind']))
with (out/'api-results.jsonl').open('w') as f:
 for c in selected:
  item={'id':c['id'],'prompt':c['prompt'],'scope':'live production API and data'};start=time.monotonic()
  try:
   req=urllib.request.Request('http://127.0.0.1:8795/api/v1/ask',data=json.dumps({'question':c['prompt'],'sampleSize':10000}).encode(),headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']})
   with urllib.request.urlopen(req,timeout=180) as resp:a=json.load(resp)
   item.update(response_type=a.get('type'),sql=a.get('sql'),reason=a.get('explanation'),compiler=(a.get('semantic') or {}).get('compiler'),row_count=a.get('rowCount'),status='LIVE_'+str(a.get('type')))
   # The first two levels have an unambiguous production metric contract.
   # More complex dimensions require separate validated business bindings.
   if c['level']<=2:
    month=c['month'];start_date=f'2026-{month:02d}-01';end_date=f'2026-{month+1:02d}-01'
    dimension='I.NAME, ' if c['level']==2 else ''
    join=' JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=S.STOCKREF' if c['level']==2 else ''
    group=' GROUP BY I.NAME' if c['level']==2 else ''
    reference=f"SELECT {dimension}SUM(CASE WHEN S.TRCODE IN (7,8) THEN S.AMOUNT ELSE 0 END) AS adet FROM dbo.LG_411_01_STLINE S{join} WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.TRCODE IN (2,3,7,8) AND S.DATE_ >= '{start_date}' AND S.DATE_ < '{end_date}'{group}"
    cols,rows,truncated=r.connector.execute(reference,10000)
    from decimal import Decimal
    def norm(rows):
     return sorted([tuple(sorted(('n',round(float(v),5)) if isinstance(v,(int,float,Decimal)) else ('s',str(v).strip()) for v in row)) for row in rows])
    values=[[row.get(col['name']) for col in cols] for row in rows]
    actual=[list(row.values()) for row in a.get('records',[])]
    ok=a.get('type')=='TEXT_TO_SQL' and not truncated and norm(values)==norm(actual)
    item.update(status='LIVE_PASS' if ok else 'LIVE_FAIL',reference_sql=reference,reference_rows=len(rows),numeric_match=ok)
   elif a.get('type')=='TEXT_TO_SQL':item['status']='LIVE_SQL_RETURNED_UNVERIFIED'
  except Exception as exc:item.update(status='LIVE_EXCEPTION',reason=str(exc)[:500])
  item['seconds']=round(time.monotonic()-start,2);f.write(json.dumps(item,ensure_ascii=False)+'\n');f.flush();print(json.dumps(item,ensure_ascii=False),flush=True)
if r.connector:r.connector.close()
