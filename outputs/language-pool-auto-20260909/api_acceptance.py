import os,json,time,hashlib,urllib.request,fcntl
from pathlib import Path
from decimal import Decimal,InvalidOperation
import sqlglot
from sqlglot import exp
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
out=Path('/data/nanobaseai/bi/backups/language-pool-auto-20260909');s=SemanticSettings.from_env();c=connector_from_file(s.connection_file)
lock=(out/'api-acceptance.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def call(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8795'+path,data=json.dumps(body).encode() if body else None,headers=headers)
 with urllib.request.urlopen(req,timeout=240) as r:return json.load(r)
def hashdoc(d):return hashlib.sha256(json.dumps(d,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
def norm(v):
 if v is None:return ('null','')
 if isinstance(v,(float,int,Decimal)):return ('number',str(Decimal(str(v)).normalize()))
 return ('text',str(v))
pool=json.loads(Path(os.environ['SEMANTIC_LANGUAGE_POOL']).read_text());old=json.loads((out/'pool-before.json').read_text());oldids={e['id'] for e in old['entries']};new=[e for e in pool['entries'] if e['id'] not in oldids]
complex_rows=json.loads(Path('/data/nanobaseai/bi/backups/language-pool-20260909/complex-final-results.json').read_text()) if Path('/data/nanobaseai/bi/backups/language-pool-20260909/complex-final-results.json').exists() else []
cases=[('A01','Satış temsilcilerinin toplam sayısı kaç?', 'SELECT COUNT(*) AS amount FROM dbo.LG_SLSMAN',['COUNT']),('A02','Satış temsilcilerinin kodlarını ve adlarını listele.','SELECT CODE,DEFINITION_ FROM dbo.LG_SLSMAN',['CODE','DEFINITION_'])]
for i,e in enumerate(new[:2],3):cases.append((f'A{i:02d}',e['phrase'],None,None))
selected=[]
for size in (7,8):
 for r in complex_rows:
  tree=sqlglot.parse_one(r['sql'],read='tsql');families={t.name.split('_')[-1] for t in tree.find_all(exp.Table)}
  if len(families)==size:
   selected.append(r)
   if sum(len({t.name.split('_')[-1] for t in sqlglot.parse_one(z['sql'],read='tsql').find_all(exp.Table)})==size for z in selected)>=2:break
for i,r in enumerate(selected,5):cases.append((f'A{i:02d}',r['prompt'],None,None))
cases += [('A09','2025 ve 2026 satış tutarlarını karşılaştır.',None,None),('A10','test',None,None)]
results=[];initial_pool=hashlib.sha256(Path(os.environ['SEMANTIC_LANGUAGE_POOL']).read_bytes()).hexdigest()
for ident,prompt,reference,keys in cases:
 started=time.monotonic();r={'id':ident,'prompt':prompt,'status':'DOĞRULANAMADI','referenceSQL':reference}
 try:
  answer=call('/api/v1/ask',{'question':prompt,'sampleSize':500,'execute':True});r['answer']=answer
  query=(answer.get('semantic') or {}).get('query') or {};r['languageHits']=len(query.get('languageCandidates') or []);r['poolHash']=query.get('languagePoolHash');r['responseType']=answer.get('type');r['sql']=answer.get('sql')
  if answer.get('resultId'):
   full=call('/api/v1/result/'+answer['resultId']);r['resultHash']=hashdoc(full);r['totalRows']=full.get('totalRows');r['truncated']=full.get('truncated');r['nullCells']=sum(v is None for row in full.get('records',[]) for v in row.values());r['zeroCells']=sum(isinstance(v,(int,float)) and v==0 for row in full.get('records',[]) for v in row.values());r['columns']=full.get('columns')
   if reference:
    refcols,truth,cut=c.execute(reference,100000);r['referenceRows']=len(truth);r['referenceTruncated']=cut
    tree=sqlglot.parse_one(answer['sql'],read='tsql');mapping={}
    for expression in tree.expressions:
     node=expression.this if isinstance(expression,exp.Alias) else expression
     key=node.name.upper() if isinstance(node,exp.Column) else 'COUNT' if isinstance(node,exp.Count) else None
     if key:mapping[key]=expression.alias_or_name
    if set(mapping)==set(keys) and set(mapping.values())=={x['name'] for x in full['columns']}:
     expected=sorted([tuple(norm(row[col['name']]) for col in refcols) for row in truth]);observed=sorted([tuple(norm(row[mapping[k]]) for k in keys) for row in full['records']]);r['referenceHash']=hashdoc(expected);r['observedHash']=hashdoc(observed)
     r['status']='LIVE_PASS' if expected==observed and not cut and not full['truncated'] and len(observed)==full['totalRows'] else 'LIVE_FAIL'
    else:r['reason']='Column lineage could not be independently matched'
   else:r['reason']='Independent business/source oracle unavailable; execution and cell statistics are not correctness certification'
  elif ident=='A10':
   r['status']='LIVE_PASS' if not answer.get('sql') and answer.get('type') in ('MODULE_INTRO','INTRO','ASSISTANT_INTRO') else 'DOĞRULANAMADI'
   r['reason']='Non-data request must not generate SQL'
  else:r['reason']='No full executable result; inspect clarification/error separately'
 except Exception as e:r['errorType']=type(e).__name__;r['error']=str(e)[:250]
 r['seconds']=round(time.monotonic()-started,2);results.append(r);(out/'api-acceptance.json').write_text(json.dumps(results,ensure_ascii=False,indent=2,default=str));print(json.dumps({k:r.get(k) for k in ('id','status','responseType','languageHits','totalRows','seconds','errorType')},ensure_ascii=False),flush=True)
summary={'questions':len(results),'statuses':{k:sum(r['status']==k for r in results) for k in ('LIVE_PASS','LIVE_FAIL','DOĞRULANAMADI')},'initialPoolFileHash':initial_pool,'finalPoolFileHash':hashlib.sha256(Path(os.environ['SEMANTIC_LANGUAGE_POOL']).read_bytes()).hexdigest(),'poolStable':initial_pool==hashlib.sha256(Path(os.environ['SEMANTIC_LANGUAGE_POOL']).read_bytes()).hexdigest()}
(out/'api-acceptance-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False));c.close()
