import collections,hashlib,json,re
from pathlib import Path
root=Path('/data/nanobaseai/bi/backups/language-pool-20260909');run=root/'live-100'
rows=[json.loads(line) for line in (run/'results.jsonl').read_text().splitlines()]
assert len(rows)==100 and len({r['id'] for r in rows})==100, 'Full 100-question acceptance is incomplete'
assert {r['id'] for r in rows}==set(json.loads((run/'manifest.json').read_text())['ids']), 'Question manifest differs'
for row in rows:
 answer_path=run/(row['id']+'.json');a=json.loads(answer_path.read_text()) if answer_path.exists() else {}
 query=(a.get('semantic') or {}).get('query') or {}
 row.update(catalogHash=query.get('catalogHash'),poolHash=query.get('languagePoolHash'),languageHits=len(query.get('languageCandidates') or []),contextScope=query.get('contextScope'))
 tables=sorted(set(re.findall(r'LG_[A-Za-z0-9_]+',row.get('sql') or '',re.I)))
 row['entities']=sorted({t.rsplit('_',1)[-1].upper() for t in tables})
 row['apiResponseHash']=hashlib.sha256(answer_path.read_bytes()).hexdigest() if answer_path.exists() else None
feature=json.loads((root/'feature-acceptance-final.json').read_text())
lookup=json.loads((root/'lookup-acceptance-final.json').read_text())
guards=json.loads((root/'context-guards.json').read_text())
scoped=json.loads((root/'scoped-acceptance-final.json').read_text())
assert len(feature+lookup+guards+scoped)==20 and len({r['id'] for r in feature+lookup+guards+scoped})==20, 'Targeted case manifest differs'
before=json.loads((root/'source-before-final.json').read_text());after=json.loads((root/'source-after-final.json').read_text())
changed=[p for p,h in before['files'].items() if after['files'].get(p)!=h]
targeted=json.loads((root/'source-before-targeted.json').read_text())
targeted_changed=[p for p,h in targeted['files'].items() if after['files'].get(p)!=h]
pool=json.loads((root/'pool-check.json').read_text())['summary']
summary={'complex':{'completed':len(rows),'counts':dict(collections.Counter(r['status'] for r in rows)),'entityCounts':dict(collections.Counter(len(r['entities']) for r in rows)),'maxFullRows':max((r.get('answer_rows',0) for r in rows),default=0),'nonemptyQuestions':sum(r.get('answer_rows',0)>0 for r in rows),'totalComparedRows':sum(r.get('answer_rows',0) for r in rows),'catalogHashes':sorted({r['catalogHash'] for r in rows if r['catalogHash']}),'poolHashes':sorted({r['poolHash'] for r in rows if r['poolHash']}),'queriesWithLanguageHits':sum(r['languageHits']>0 for r in rows)},'targetedCounts':dict(collections.Counter(r['status'] for r in feature+lookup+guards+scoped)),'featureCounts':dict(collections.Counter(r['status'] for r in feature)),'lookupCounts':dict(collections.Counter(r['status'] for r in lookup)),'scopedCounts':dict(collections.Counter(r['status'] for r in scoped)),'contextGuardCounts':dict(collections.Counter(r['status'] for r in guards)),'sourceChangedDuringAcceptance':changed,'sourceChangedSinceTargeted':targeted_changed,'sameTargetedServiceProcess':targeted['health']['pid']==after['health']['pid'],'sameServiceProcess':before['health']['pid']==after['health']['pid'],'retrieval':pool,'unscopedLookupInitialOracle':'DOĞRULANAMADI: original reference assumed both firms without establishing the default period scope; final tests explicitly ask firm 411.'}
(root/'final-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
(root/'complex-final-results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
compact=[]
for r in feature+lookup+guards+scoped:
 a=r.get('answer',{});sq=(a.get('semantic') or {}).get('query') or {};full=r.get('fullResult',{})
 compact.append({k:r.get(k) for k in ['id','question','status','languageHits','poolHash','referenceSQL','seconds','error','referenceRows','answerRows']}|{'catalogHash':sq.get('catalogHash'),'poolHash':sq.get('languagePoolHash'),'languageHits':len(sq.get('languageCandidates') or []),'responseType':a.get('type'),'explanation':a.get('explanation'),'sql':a.get('sql'),'physicalSql':a.get('physicalSql'),'contextScope':sq.get('contextScope'),'resultId':a.get('resultId'),'totalRows':full.get('totalRows'),'truncated':full.get('truncated'),'fullResultHash':hashlib.sha256(json.dumps(full,ensure_ascii=False,sort_keys=True).encode()).hexdigest() if full else None})
(root/'feature-final-results.json').write_text(json.dumps(compact,ensure_ascii=False,indent=2))
lines=['# Son soru listesi ve statüler','', '100 karmaşık regresyon sorusu ve 20 hedefli kontrol. LIVE_PASS: tam API sonucu bağımsız bağlı DB referansıyla eşleşti. GUARD_PASS: beklenen netleştirme/veri yok davranışı; sayısal başarı değildir. NO_NUMERIC_ANSWER: soru cevaplanamadı, açık sorun. Başarısız veya doğrulanamayan kayıtlar başarıya dahil değildir.','', '| Kimlik | Soru | Statü | Tablo türü | Tam satır |','|---|---|---|---:|---:|']
for r in rows:lines.append(f"| {r['id']} | {r['prompt'].replace('|',' / ')} | {r['status']} | {len(r['entities'])} | {r.get('answer_rows','—')} |")
for r in compact:lines.append(f"| {r['id']} | {r['question'].replace('|',' / ')} | {r['status']} | — | {r.get('totalRows') if r.get('totalRows') is not None else '—'} |")
(root/'prompts-final-status.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,ensure_ascii=False),flush=True)
