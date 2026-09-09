import hashlib,json,os,sys,urllib.request
from pathlib import Path
root=Path('/data/nanobaseai/bi/backups/language-pool-20260909');sys.path.insert(0,'/data/nanobaseai/bi/frontend/tests/stress')
from enduser_10000 import corpus
from result_comparison import aligned_rows,norm
cases={c['id']:c for c in corpus()};rows=json.loads((root/'complex-final-results.json').read_text());evidence=[]
for row in [r for r in reversed(rows) if r['metric']=='net satış tutarı'][:3]:
 answer=json.loads((root/'live-100'/(row['id']+'.json')).read_text())
 req=urllib.request.Request('http://127.0.0.1:8795/api/v1/result/'+answer['resultId'],headers={'X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']})
 with urllib.request.urlopen(req,timeout=120) as resp: full=json.load(resp)
 aligned=aligned_rows(full,cases[row['id']]);digest=hashlib.sha256(repr(norm(aligned)).encode()).hexdigest()
 assert digest==row['answer_sha256']==row['reference_sha256'] and not full['truncated'] and len(aligned)==full['totalRows']
 item={'id':row['id'],'resultId':answer['resultId'],'rows':len(aligned),'nullCells':sum(v is None for r in aligned for v in r),'numericZeroCells':sum(isinstance(v,(int,float)) and not isinstance(v,bool) and v==0 for r in aligned for v in r),'resultHash':digest,'sameOriginalExecutionVerified':True}
 evidence.append(item)
 if item['nullCells'] and item['numericZeroCells']:break
(root/'result-cell-evidence.json').write_text(json.dumps({'source':'Existing full result IDs from completed acceptance; no SQL re-execution','subset':evidence},indent=2))
print(json.dumps(evidence))
