#!/usr/bin/env python3
"""Rebuild a restored installation's search index from real PostgreSQL passages.

Run on the destination server after restore, with the destination project name.
The source installation and its historical analysis records are not rewritten.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
os.chdir(root)
if len(sys.argv)!=2:
    raise SystemExit('Usage: rebuild-search.py EXACT_COMPOSE_PROJECT_NAME')
config=json.loads(subprocess.check_output(['docker','compose','config','--format','json']))
if config['name']!=sys.argv[1]: raise SystemExit('Project name mismatch')
code=r'''
import json, math
import httpx
from editor.config import connection
from editor.retrieval import embed, COLLECTION
from editor.book_store import get_records

with connection() as db:
    if db.execute("SELECT id FROM editor.jobs WHERE status IN ('RUNNING','QUEUED') LIMIT 1").fetchone():
        raise RuntimeError('QUIESCE_JOBS_BEFORE_SEARCH_REBUILD')
    generations=db.execute("SELECT id FROM editor.generations WHERE status IN ('VALIDATED','ACTIVE','RETIRED') ORDER BY created_at").fetchall()
report=[]
with httpx.Client(timeout=180,trust_env=False) as client:
    response=client.get(f'http://qdrant:6333/collections/{COLLECTION}')
    if response.status_code==404:
        client.put(f'http://qdrant:6333/collections/{COLLECTION}',json={'vectors':{'size':1024,'distance':'Cosine'}}).raise_for_status()
    else:
        response.raise_for_status()
        vectors=response.json()['result']['config']['params']['vectors']
        if vectors.get('size')!=1024 or vectors.get('distance')!='Cosine':
            raise RuntimeError('RESTORE_VECTOR_SPACE_MISMATCH')
    for generation in generations:
        gen=generation['id']; sources={str(r['id']) for r in get_records(gen,'evidence')}
        passages=get_records(gen,'passages')
        if len(passages)!=len(sources): raise RuntimeError('RESTORE_PASSAGE_COVERAGE_MISMATCH')
        for passage in passages:
            data=passage['data']; refs=data['evidence_refs']
            if len(refs)!=1 or refs[0] not in sources: raise RuntimeError('RESTORE_BROKEN_PASSAGE_SOURCE')
            vector=embed(data['text'])
            if not all(math.isfinite(x) for x in vector): raise RuntimeError('INVALID_EMBEDDING')
            rid=str(passage['id']); payload={'generation_id':str(gen),'evidence_id':refs[0]}
            client.put(f'http://qdrant:6333/collections/{COLLECTION}/points',params={'wait':'true'},
                json={'points':[{'id':rid,'vector':vector,'payload':payload}]}).raise_for_status()
            # Verify the actual restored point, including its source scope and vector.
            response=client.post(f'http://qdrant:6333/collections/{COLLECTION}/points',
                json={'ids':[rid],'with_payload':True,'with_vector':True})
            response.raise_for_status(); points=response.json()['result']
            if len(points)!=1 or points[0]['payload']!=payload: raise RuntimeError('RESTORE_POINT_SCOPE_MISMATCH')
            actual=points[0]['vector']
            cosine=sum(a*b for a,b in zip(actual,vector))/(math.sqrt(sum(x*x for x in actual))*math.sqrt(sum(x*x for x in vector)))
            if len(actual)!=len(vector) or cosine<0.99999: raise RuntimeError('RESTORE_VECTOR_MISMATCH')
            with connection() as db:
                db.execute('UPDATE editor.outbox SET delivered_at=now() WHERE id=%s',(rid,))
        response=client.post(f'http://qdrant:6333/collections/{COLLECTION}/points/count',
            json={'exact':True,'filter':{'must':[{'key':'generation_id','match':{'value':str(gen)}}]}})
        response.raise_for_status()
        if response.json()['result']['count']!=len(passages): raise RuntimeError('RESTORE_INDEX_COUNT_MISMATCH')
        report.append({'generation_id':str(gen),'verified_passages_and_vectors':len(passages)})
print(json.dumps({'rebuilt_generations':report,'semantic_acceptance':False}))
'''
result=subprocess.check_output(['docker','compose','exec','-T','api','python','-'],input=code,text=True)
report=json.loads(result)
(root/'evidence').mkdir(exist_ok=True)
(root/'evidence/search-rebuild.json').write_text(json.dumps(report,indent=2))
print(result,end='')
