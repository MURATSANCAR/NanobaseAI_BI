import os,json,urllib.request
from pathlib import Path
req=urllib.request.Request('http://127.0.0.1:8795/api/v1/schema/inventory?limit=2&columns=false',headers={'X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']})
with urllib.request.urlopen(req,timeout=60) as r:d=json.load(r)
contexts=[t.get('context') for t in d.get('tables',[])]
report={'tableCount':d.get('tableCount'),'total':d.get('total'),'contexts':contexts,'patternLabels':os.environ.get('SEMANTIC_PATTERN_LABELS'),'context_has_firma':any('firma' in json.dumps(c).lower() for c in contexts)}
root=Path(os.environ['SEMANTIC_KNOWLEDGE_DIR'])/'knowledge'
parts=[p.read_text() for p in sorted(root.rglob('*.md')) if p.parent.name not in {'sql','reference'}]
report['first_rule_single_company']='Tek şirket vardır.' in parts[0]
report['old_only_2026_claim']=any('Veri yalnız 2026 (firma 411' in s for s in parts)
p=Path('/data/nanobaseai/bi/backups/source-topology-20260909/api-verification.json');p.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(p.read_text())
