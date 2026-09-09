import json,os
from pathlib import Path
from semantic_bridge.app import build_runtime
r=build_runtime();pool=r.language_pool;old=json.loads(Path('/data/nanobaseai/bi/backups/language-pool-auto-20260909/pool-before.json').read_text());ids={e['id'] for e in old['entries']};rows=[]
for e in pool.entries:
 if e['id'] in ids:continue
 hits=pool.search(e['phrase']);rows.append({'id':e['id'],'phrase':e['phrase'],'columns':e['columns'],'exactRetrieved':any(h['id']==e['id'] for h in hits),'ambiguities':e['ambiguities']})
report={'poolHash':pool.content_hash,'totalCandidates':len(pool.entries),'newCandidates':len(rows),'staleRejected':pool.rejected,'exactRetrieved':sum(x['exactRetrieved'] for x in rows),'rows':rows,'scope':'Actual deployed runtime, real catalog; retrieval evidence, not numeric acceptance'}
Path('/data/nanobaseai/bi/backups/language-pool-auto-20260909/reviewed-pool-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False));r.connector.close()
