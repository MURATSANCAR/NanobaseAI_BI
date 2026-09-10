import json, hashlib
from pathlib import Path
from semantic_bridge.app import build_runtime
from semantic_layer.models import SemanticQuery
root=Path('/data/nanobaseai/bi/backups/language-pool-20260909')
r=build_runtime(); pool=r.language_pool; compiler=r.existing
assert pool and not pool.rejected
reports=[]
for entry in pool.entries:
 q=SemanticQuery(entry['phrase'],r.settings.tenant_id,r.settings.datasource_id)
 target={(c['entity'],c['column']) for c in entry['columns']}
 hits=pool.search(q.question);base={(h['entity'],h['column'].upper()) for h in compiler.columns.search(q.question,limit=compiler.column_focus_tail)} if compiler.columns else set()
 expanded=base|{(c['entity'],c['column']) for h in hits for c in h['columns']}
 row={'id':entry['id'],'phrase':entry['phrase'],'status':'SCHEMA_SEARCH_CHECKED','targetColumns':len(target),'baseCovered':len(target&base),'expandedCovered':len(target&expanded),'exactRetrieved':any(h['id']==entry['id'] for h in hits),'ambiguities':entry['ambiguities'],'columns':entry['columns']}
 reports.append(row)
summary={'poolHash':pool.content_hash,'poolCandidates':len(reports),'sourceRejected':pool.rejected,'selfRetrieval':sum(x['exactRetrieved'] for x in reports),'targetColumns':sum(x['targetColumns'] for x in reports),'baseCovered':sum(x['baseCovered'] for x in reports),'expandedCovered':sum(x['expandedCovered'] for x in reports),'phrasesImproved':sum(x['expandedCovered']>x['baseCovered'] for x in reports),'note':'Generated phrase/reference pairs test schema retrieval only, not independent business correctness.'}
(root/'pool-check.json').write_text(json.dumps({'summary':summary,'entries':reports},ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False),flush=True)
if r.connector:r.connector.close()
