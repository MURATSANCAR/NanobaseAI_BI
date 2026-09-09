"""Join evidence by prompt ID without converting unexecuted cases into successes."""
import json,csv,collections
from pathlib import Path
root=Path(__file__).resolve().parents[2]
a=root/'artifacts/enduser-10000'
out=root/'outputs/enduser-10000-20260909';out.mkdir(parents=True,exist_ok=True)
def rows(path):return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
def keyed(path):return {r['id']:r for r in rows(path)}
controlled=rows(a/'acceptance-final/results.jsonl')
before=keyed(a/'before/results.jsonl')
ready=keyed(a/'readiness-final/readiness.jsonl')
live=keyed(a/'live-final/results.jsonl')
live.update(keyed(a/'live-extra-final/results.jsonl'))
model_before=keyed(a/'model-before/results.jsonl');model_after=keyed(a/'model-after/results.jsonl')
assert len(controlled)==len(ready)==10000
assert len(live)==16
assert len({r['prompt'] for r in controlled})==10000
result=[]
for r in controlled:
 q={k:r.get(k) for k in ['id','level','prompt','year','month','metric','kind','dimensions','expected_tables','expected_table_count','expected_joins','family','status','model_calls','seconds','sql']}
 q.update(before_status=before[r['id']]['status'],readiness_status=ready[r['id']]['status'],readiness_reason=ready[r['id']].get('reason'),live_status='NOT_LIVE_TESTED',controlled_scope='Generated fixture; independent Python result oracle')
 if r['id'] in live:
  l=live[r['id']];q.update(live_status=l['status'],live_reason=l.get('reason') or ('Tam SQL sonucu eşleşti; API önizlemesi 500 satırla sınırlı.' if l.get('preview_truncated') else 'Tam sonuç eşleşti.' if l.get('numeric_match') else 'Doğrulama başarısız.'),live_seconds=l['seconds'],live_reference_rows=l.get('reference_rows'),live_answer_rows=l.get('answer_rows'))
 q.update(model_before_status=model_before.get(r['id'],{}).get('status','NOT_MODEL_TESTED'),model_after_status=model_after.get(r['id'],{}).get('status','NOT_MODEL_TESTED'))
 result.append(q)
(out/'final-list.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
fields=['id','level','prompt','expected_table_count','expected_joins','status','before_status','readiness_status','readiness_reason','live_status','live_reason','model_calls','seconds']
with (out/'10000-prompt-sonuclari.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(result)
summary={k:dict(collections.Counter(r[k] for r in result)) for k in ['status','before_status','readiness_status','live_status','expected_table_count']}
(out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False))
