"""Merge actual API/DB attempts without mixing controlled acceptance results."""
import argparse,collections,json
from pathlib import Path

def build(root):
    attempts=collections.defaultdict(list)
    for path in [root/'results.jsonl',*sorted(root.glob('retry-*/results.jsonl'))]:
        if not path.exists():continue
        lines=path.read_text().splitlines()
        for i,line in enumerate(lines):
            try:item=json.loads(line)
            except json.JSONDecodeError:
                if i==len(lines)-1:continue
                raise
            item=dict(item,attempt_source=str(path.relative_to(root)))
            attempts[item['id']].append(item)
    rows=[]
    for i in range(1,10001):
        identifier=f'P{i:05d}'
        history=sorted(attempts[identifier],key=lambda x:x.get('started_at',''))
        latest=history[-1] if history else {'id':identifier,'status':'NOT_LIVE_TESTED'}
        rows.append(dict(latest,attempt_count=len(history),previous_statuses=[x['status'] for x in history[:-1]]))
    counts=dict(collections.Counter(x['status'] for x in rows))
    summary={'total':10000,'tested_unique':sum(x['attempt_count']>0 for x in rows),'counts':counts,'scope':'Actual production API and connected database; latest recorded attempt per prompt'}
    return summary,rows

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    summary,rows=build(a.root);a.out.mkdir(parents=True,exist_ok=True)
    for name,data in [('summary.json',summary),('current-list.json',rows)]:
        temp=a.out/(name+'.tmp');temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.replace(a.out/name)
    print(json.dumps(summary,ensure_ascii=False))
