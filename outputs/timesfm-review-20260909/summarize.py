import json
from pathlib import Path
root=Path(__file__).parent
data=[json.loads(line) for line in (root/'profile.jsonl').read_text().splitlines()]
out=[]
for d in data:
    rows=d.get('rows',[])
    if not any('year' in r for r in rows): continue
    valid=[r for r in rows if r.get('year')]
    years={}
    for r in valid:
        y=years.setdefault(str(r['year']),dict(rows=0,sale_rows=0,return_rows=0,months=[]))
        for k in ['rows','sale_rows','return_rows']: y[k]+=r.get(k,0)
        y['months'].append(r['month'])
    out.append(dict(source=d['label'],first=min(r['first_date'] for r in valid),last=max(r['last_date'] for r in valid),null_date_rows=sum(r['rows'] for r in rows if not r.get('year')),years=years))
result=dict(sources=out,errors=[d for d in data if 'error' in d],completed_queries=len(data))
(root/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False,indent=2))
