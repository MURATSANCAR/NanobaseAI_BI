#!/usr/bin/env python3
"""Verify full real answer API records against PostgreSQL, without grading semantics."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request

root=Path(__file__).resolve().parents[1]; os.chdir(root)
run=json.loads((root/'evidence/reference-book-run.json').read_text())
gen=run['job']['generation_id']; output=root/'runtime/book-analysis'/gen
jobs=json.loads((output/'question-jobs.json').read_text())
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}

def get(path):
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8810'+path,headers=headers),timeout=30) as response:
        return json.load(response)

def sql(query):
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))

reference=sql("SELECT COALESCE(json_agg(json_build_object('id',j.id,'status',j.status,'question',j.payload->>'question','error_code',j.error_code,'answer',r.data) ORDER BY j.created_at,j.id),'[]'::json) FROM editor.jobs j LEFT JOIN editor.records r ON r.generation_id=j.generation_id AND r.kind='answers' AND r.record_key=j.id::text WHERE j.generation_id='"+gen+"' AND j.task='question'")
listed=[];offset=0
while True:
    page=get(f'/v1/question-jobs?generation_id={gen}&offset={offset}&limit=100')
    listed.extend(page['items'])
    if not page['has_more']: break
    offset+=len(page['items'])
assert listed==reference, 'Full question list API differs from independent PostgreSQL'
by_id={r['id']:r for r in reference}
sources=sql("SELECT json_object_agg(id,data) FROM editor.records WHERE generation_id='"+gen+"' AND kind='evidence'")
checks=[]
for key,job in jobs.items():
    actual=get('/v1/answers/'+job['job_id']); expected=by_id[job['job_id']]
    assert actual['generation_id']==gen and actual['job_status']==expected['status']
    assert actual['answer']==expected['answer'], 'Full answer API differs from stored execution'
    answer=actual['answer']; citations=0
    if expected['status']=='COMPLETED': assert answer is not None, 'Completed question has no answer'
    if answer:
        assert answer['generation_id']==gen and answer['question']==expected['question']
        for evidence in answer['retrieved_evidence']:
            source=sources[evidence['evidence_id']]
            assert evidence['pdf_page']==source['pdf_page']
            assert evidence['text']==source['ocr_text'] and evidence['text_layer']==source['text_layer']
        allowed={e['evidence_id'] for e in answer['retrieved_evidence']}
        for claim in answer['claims']:
            assert claim['evidence_refs'] and set(claim['evidence_refs'])<=allowed
            citations+=len(claim['evidence_refs'])
    checks.append({'scenario':key,'job_id':job['job_id'],'status':expected['status'],
                   'full_api_equals_independent_db':True,'resolved_citations':citations})
result={'environment':'real remote Editor API and independent PostgreSQL','generation_id':gen,
        'checks':checks,'semantic_acceptance':'REQUIRES_INDEPENDENT_SOURCE_COMPARISON',
        'human_accepted':False}
(root/'evidence/book-answers-integrity.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
