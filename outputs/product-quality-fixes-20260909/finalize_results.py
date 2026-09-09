import json,csv,collections,re,statistics
from pathlib import Path
import sys
root=Path(sys.argv[1]); rows=[json.loads(line) for line in (root/'results.jsonl').read_text().splitlines()]
byid={r['id']:r for r in rows};rows=list(byid.values())
for row in rows:
 tables=set(re.findall(r'(?:FROM|JOIN)\s+(?:dbo\.)?(LG_[A-Z0-9_]+)',row.get('reference_sql',''),re.I))
 entities={re.sub(r'^LG_(?:[0-9]+_)*','',t) for t in tables}
 row['physical_table_count']=len(tables);row['entity_count']=len(entities)
(root/'final-list.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
fields=['id','prompt','status','metric','level','entity_count','physical_table_count','answer_rows','reference_rows','numeric_match','seconds','answer_sha256','reference_sha256']
with (root/'final-list.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
counts=dict(collections.Counter(r['status'] for r in rows));dur=sorted(r['seconds'] for r in rows)
summary={'completed':len(rows),'counts':counts,'maxRows':max((r.get('answer_rows',0) for r in rows),default=0),'minRows':min((r.get('answer_rows',0) for r in rows),default=0),'medianEndToEndSeconds':statistics.median(dur) if dur else None,'p95EndToEndSeconds':dur[max(0,__import__('math').ceil(len(dur)*.95)-1)] if dur else None,'scope':'Eight-table aggregate questions; actual API snapshots vs independent connected DB references. Durations include reference query and full transfer, not API latency.'}
(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
lines=['# 100 karmaşık soru — gerçek API/DB doğrulaması','',json.dumps(counts,ensure_ascii=False),'','| ID | Soru | Durum | Satır |','|---|---|---|---|']
lines += [f"| {r['id']} | {r['prompt'].replace('|','/')} | {r['status']} | {r.get('answer_rows','—')} |" for r in rows]
(root/'final-list.md').write_text('\n'.join(lines)+'\n')
print(json.dumps(summary,ensure_ascii=False))
