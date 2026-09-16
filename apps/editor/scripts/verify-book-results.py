#!/usr/bin/env python3
"""Independent, read-only deployed API/DB/artifact integrity check of a real run."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

root=Path(__file__).resolve().parents[1]; os.chdir(root)
run=json.loads((root/'evidence/reference-book-run.json').read_text())
gen=run['job']['generation_id']; token=(root/'secrets/api_token').read_text().strip()
base='http://127.0.0.1:8810'


def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers={'Authorization':'Bearer '+token}),timeout=30) as response: return json.load(response)


def sql(query):
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))


records={}; checks=[]
for kind in ('evidence','visuals','scenes','entities','events','literary','validation','passages',
             'claims','relationships','event_merges','book_synthesis'):
    data=[]; offset=0
    while True:
        page=get(f'/v1/generations/{gen}/{kind}?offset={offset}&limit=100'); data.extend(page['items'])
        if not page['has_more']: break
        offset+=len(page['items'])
    reference=sql("SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='"+gen+"' AND kind='"+kind+"'")
    # Counts can change during a live visual pass; only compare stable matched snapshots.
    if data!=reference:
        page=get(f'/v1/generations/{gen}/{kind}?limit=100')
        if not page['has_more']: data=page['items']
    assert data==reference,kind+' full API output differs from independent PostgreSQL'
    records[kind]=data
    checks.append({'kind':kind,'count':len(data),'api_equals_independent_db':True})

evidence={r['id']:r['data'] for r in records['evidence']}
refs=0


def inspect(value):
    global refs
    if isinstance(value,dict):
        for key,item in value.items():
            if key in ('evidence_refs','counter_evidence_refs'):
                for rid in item:
                    assert rid in evidence, 'Broken or cross-generation citation'
                    refs+=1
            else: inspect(item)
    elif isinstance(value,list):
        for item in value: inspect(item)


for rows in records.values():
    for row in rows: inspect(row['data'])

code='''import hashlib,json,pathlib,sys
from editor.config import connection
with connection() as db: rows=db.execute("SELECT data FROM editor.records WHERE generation_id=%s AND kind='evidence'",(sys.argv[1],)).fetchall()
for row in rows:
 d=row['data']; root=pathlib.Path('/data/artifacts')/d['source_sha256']; p=root/'ocr-regions-v2'/('page-%04d.json'%d['pdf_page']); raw=p.read_bytes(); original=json.loads(raw)
 assert hashlib.sha256(raw).hexdigest()==d['ocr_artifact_sha256']
 assert original['text']==d['ocr_text'] and original['blocks']==d['blocks']
 assert '\\t' not in d['ocr_text']
 assert hashlib.sha256(p.with_suffix('.png').read_bytes()).hexdigest()==d['ocr_render_sha256']
 assert hashlib.sha256((root/('page-%04d.png'%d['pdf_page'])).read_bytes()).hexdigest()==d['render_sha256']
print(json.dumps({'artifact_verified_pages':len(rows)}))'''
artifact=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,gen],text=True))
job=get('/v1/jobs/'+run['job']['job_id'])
result={'environment':'remote nanobase-direct / real editor PostgreSQL and HTTP API','generation_id':gen,
        'job_status':job['status'],'counts_and_full_values':checks,'resolved_citations':refs,**artifact,
        'semantic_acceptance':'NOT_ESTABLISHED_BY_STRUCTURAL_CHECK','human_accepted':False}
(root/'evidence/book-results-integrity.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
