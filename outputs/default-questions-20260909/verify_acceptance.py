import hashlib,json,sys
from pathlib import Path
root=Path('/data/nanobaseai/bi/backups/default-questions-20260909');run=root/'live-100-accepted'
expected=json.loads((run/'manifest.json').read_text())['ids']
rows=[json.loads(x) for x in (run/'results.jsonl').read_text().splitlines()]
errors=[]
if len(expected)!=100 or len(rows)!=100 or sorted(r['id'] for r in rows)!=sorted(expected):errors.append('Exactly 100 selected unique questions required')
for row in rows:
 if row.get('status') not in ('LIVE_PASS','LIVE_PASS_SQL_PREVIEW_LIMITED'):errors.append(row['id']+': '+row.get('status','MISSING'))
 if row.get('answer_sha256')!=row.get('reference_sha256') or not row.get('numeric_match'):errors.append(row['id']+': result/reference mismatch')
 if row.get('answer_rows')!=row.get('reference_rows'):errors.append(row['id']+': row count mismatch')
for path,digest in json.loads((root/'source-manifest.json').read_text())['files'].items():
 if '/backend/' not in path:continue
 p=Path(path)
 if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:errors.append('Changed production source: '+path)
runner=Path('/data/nanobaseai/bi/frontend/tests/stress/enduser_live_10000.py')
runner_hash=hashlib.sha256(runner.read_bytes()).hexdigest()
if {r.get('runner_sha256') for r in rows}!={runner_hash}:errors.append('Acceptance runner source changed')
hashes=set()
for row in rows:
 p=run/(row['id']+'.json')
 if not p.exists():errors.append('Missing API response: '+row['id']);continue
 answer=json.loads(p.read_text());hashes.add(((answer.get('semantic') or {}).get('query') or {}).get('catalogHash'))
 if answer.get('type')!='TEXT_TO_SQL' or not answer.get('resultId'):errors.append('Missing execution identity: '+row['id'])
if len(hashes)!=1 or None in hashes:errors.append('Catalog changed during acceptance')
result={'status':'PASS' if not errors else 'FAIL','count':len(rows),'catalogHashes':sorted(str(h) for h in hashes),'errors':errors}
(root/'acceptance-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));sys.exit(bool(errors))
