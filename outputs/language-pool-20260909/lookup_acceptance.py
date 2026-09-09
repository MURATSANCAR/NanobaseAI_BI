import json,os,time,urllib.request
from pathlib import Path
from decimal import Decimal
import sqlglot
from sqlglot import exp
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
root=Path('/data/nanobaseai/bi/backups/language-pool-20260909');s=SemanticSettings.from_env();c=connector_from_file(s.connection_file)
headers={'Content-Type':'application/json','X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def call(path,body=None):
 req=urllib.request.Request('http://127.0.0.1:8795'+path,data=json.dumps(body).encode() if body else None,headers=headers)
 with urllib.request.urlopen(req,timeout=240) as r:return json.load(r)
# The API spans the two active catalogs for an undated logical master table.
# These references count physical cards; they do not deduplicate cross-firm numeric IDs.
base=' UNION ALL '.join(f'SELECT CODE,DEFINITION_,PPGROUPCODE FROM dbo.LG_{f}_PAYPLANS' for f in ['211','411'])
cases=[('L11','Ödeme planı kodu ve açıklaması', 'SELECT CODE,DEFINITION_ FROM ('+base+') P',['CODE','DEFINITION_']),
       ('L12','Ödeme planı grup koduna göre sayı', 'SELECT PPGROUPCODE,COUNT(*) amount FROM ('+base+') P GROUP BY PPGROUPCODE',['PPGROUPCODE','COUNT'])]
rows=[]
for ident,q,ref,identities in cases:
 row={'id':ident,'question':q,'referenceSQL':ref,'status':'DOĞRULANAMADI'};start=time.monotonic()
 try:
  a=call('/api/v1/ask',{'question':q,'sampleSize':100000});row['answer']=a
  query=(a.get('semantic') or {}).get('query') or {};row['poolHash']=query.get('languagePoolHash');row['languageHits']=len(query.get('languageCandidates') or [])
  cols,truth,tr=c.execute(ref,100000);row['referenceRows']=len(truth)
  if a.get('resultId'):
   full=call('/api/v1/result/'+a['resultId']);row['fullResult']=full
   tree=sqlglot.parse_one(a['sql'],read='tsql');select=tree if isinstance(tree,exp.Select) else None
   mapping={}
   if select:
    for expr in select.expressions:
     node=expr.this if isinstance(expr,exp.Alias) else expr
     key=node.name.upper() if isinstance(node,exp.Column) else 'COUNT' if isinstance(node,exp.Count) else None
     if key:mapping[key]=expr.alias_or_name
   if set(mapping)==set(identities) and set(mapping.values())=={x['name'] for x in full['columns']}:
    expected=sorted([tuple(str(r[col['name']]) if r[col['name']] is not None else None for col in cols) for r in truth],key=str)
    actual=sorted([tuple(str(r[mapping[k]]) if r[mapping[k]] is not None else None for k in identities) for r in full['records']],key=str)
    row['status']='LIVE_PASS' if expected==actual and not tr and not full['truncated'] and len(actual)==full['totalRows'] else 'LIVE_FAIL'
    row['reference']=expected;row['observed']=actual
   else:row['status']='UNVERIFIED_COLUMN_LINEAGE'
  else:row['status']='NO_NUMERIC_OR_LOOKUP_ANSWER'
 except Exception as e:row['error']=str(e)[:500]
 row['seconds']=round(time.monotonic()-start,2);rows.append(row)
 (root/'lookup-acceptance.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=str))
 print(json.dumps({k:row.get(k) for k in ['id','status','languageHits','seconds','error']},ensure_ascii=False),flush=True)
c.close()
