import json,hashlib,collections,re
from pathlib import Path
root=Path('/data/nanobaseai/bi/backups/default-questions-20260909')
run=root/'live-100-accepted'
rows=[json.loads(line) for line in (run/'results.jsonl').read_text().splitlines()]
for row in rows:
 answer=json.loads((run/(row['id']+'.json')).read_text()) if (run/(row['id']+'.json')).exists() else {}
 query=(answer.get('semantic') or {}).get('query') or {}
 row['catalogHash']=query.get('catalogHash');row['catalogVersion']=query.get('catalogVersion')
 tables=sorted(set(re.findall(r'LG_[A-Za-z0-9_]+',row.get('sql') or '',re.I)))
 row['physical_tables']=tables;row['entities']=sorted({t.rsplit('_',1)[-1].upper() for t in tables})
 row['api_response_sha256']=hashlib.sha256((run/(row['id']+'.json')).read_bytes()).hexdigest() if answer else None
(root/'complex-final-results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
counts=dict(collections.Counter(r['status'] for r in rows))
summary={'completed':len(rows),'counts':counts,'catalogHashes':sorted({r['catalogHash'] for r in rows if r['catalogHash']}),'entityCounts':dict(collections.Counter(len(r['entities']) for r in rows))}
(root/'complex-final-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
lines=['# Karmaşık soru listesi ve statüler','', 'Gerçek üretim API tam sonuçları, bağımsız DB referansı ile karşılaştırıldı.','', '| Kimlik | Soru | Statü | Tablo türü | Sonuç satırı |','|---|---|---|---:|---:|']
for r in rows:lines.append('| '+r['id']+' | '+r['prompt'].replace('|',' / ')+' | '+r['status']+' | '+str(len(r['entities']))+' | '+str(r.get('answer_rows','—'))+' |')
(root/'prompts-final-status.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,ensure_ascii=False))
