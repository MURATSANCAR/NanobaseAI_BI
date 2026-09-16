#!/usr/bin/env python3
"""Read-only acceptance of the deployed page pipeline using actual API/PG records."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/'evidence/source-spans-run.json').read_text());gen=run['generation_id']
base=os.environ.get('EDITOR_VERIFY_BASE_URL','http://127.0.0.1:8810')
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=60) as r: return json.load(r)
def rows(kind,page=None):
    result=[];offset=0
    while True:
        data=get(f'/v1/generations/{gen}/{kind}?offset={offset}&limit=100'+(f'&pdf_page={page}' if page else ''))
        result+=data['items']
        if not data['has_more']:return result
        offset+=len(data['items'])
def sql(query):
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))

readings=rows('page_readings');checks=[]
# Freeze the completed-page boundary: the worker may append the next page during
# this read-only audit. Completed page records are immutable.
completed={r['data']['pdf_page'] for r in rows('page_checks')}
for reading in readings:
    page=reading['data']['pdf_page']
    kinds=('source_spans','layout_regions','page_readings')
    if page in completed:kinds+=('visual_observations','page_claims','page_checks')
    for kind in kinds:
        api=rows(kind,page)
        db=sql("SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='"+gen+"' AND kind='"+kind+"' AND data->>'pdf_page'='"+str(page)+"'")
        assert api==db, f'API_DB_MISMATCH:{kind}:{page}'
        if kind=='source_spans':
            assert len(api)==reading['data']['span_count']
            for r in api:
                d=r['data'];assert d['render_sha256']==reading['data']['render_sha256']
                x,y,w,h=d['bbox'];assert min(x,y,w,h)>=0 and x+w<=1.001 and y+h<=1.001
    checks.append({'page':page,'api_db_equal':True,'verified_kinds':list(kinds),
                   **{k:reading['data'][k] for k in ('span_count','agreed_spans','review_spans','status')}})
assert not rows('visuals'), 'OLD_VISUAL_CAPTIONS_PRESENT'
assert not rows('claims') and not rows('events'), 'UNACCEPTED_FACTS_MATERIALIZED'
for row in rows('page_claims'):
    assert row['data']['input_visual_descriptions'] is False
    for c in row['data']['claims']+row['data']['blocked_claims']:
        assert c['eligible_for_synthesis'] is False
        assert c['speaker'] is None
reviews=sql("SELECT count(*) FROM editor.reviews WHERE generation_id='"+gen+"'")
assert reviews==0 and not rows('visual_corrections')
job=get('/v1/jobs/'+run['job_id'])
if job['status']=='COMPLETED':
    expected=set(range(1,job['source_coverage']['expected_pages']+1))
    assert set(r['data']['pdf_page'] for r in readings)==expected,'INCOMPLETE_SOURCE_PAGES'
    assert completed==expected,'INCOMPLETE_PAGE_CHECKS'
report={'generation_id':gen,'job_status':job['status'],'api':base,'checks':checks,
    'checked_at':datetime.now(timezone.utc).isoformat(),
    'old_visual_descriptions':0,'manual_reviews':0,'source_corrections':0,
    'semantic_acceptance':False,'counts':job['counts']}
(root/'evidence/source-spans-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
