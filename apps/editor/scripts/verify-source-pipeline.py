#!/usr/bin/env python3
"""Read-only acceptance of the deployed page pipeline using actual API/PG records."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from datetime import datetime, timezone

root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/os.environ.get('EDITOR_VERIFY_RUN_FILE','evidence/source-spans-run.json')).read_text());gen=run['generation_id']
base=os.environ.get('EDITOR_VERIFY_BASE_URL','http://127.0.0.1:8810')
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=60) as r: return json.load(r)
api_cache={};db_cache={}
def rows(kind,page=None):
    if snapshot_job['status']=='COMPLETED':
        if kind in api_cache:return [r for r in api_cache[kind] if page is None or r['data']['pdf_page']==page]
        if page is not None:return [r for r in rows(kind) if r['data']['pdf_page']==page]
    result=[];offset=0
    while True:
        data=get(f'/v1/generations/{gen}/{kind}?offset={offset}&limit=100'+(f'&pdf_page={page}' if page else ''))
        result+=data['items']
        if not data['has_more']:
            if snapshot_job['status']=='COMPLETED':api_cache[kind]=result
            return result
        offset+=len(data['items'])
def sql(query):
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))

snapshot_job=get('/v1/jobs/'+run['job_id'])
readings=rows('page_readings');checks=[]
# Freeze the completed-page boundary: the worker may append the next page during
# this read-only audit. Completed page records are immutable.
completed={r['data']['pdf_page'] for r in rows('page_checks')}
for reading in readings:
    page=reading['data']['pdf_page']
    kinds=('source_spans','layout_regions','page_readings')
    if page in completed:
        kinds+=('visual_observations','page_claims','page_checks')
        if reading['data'].get('pipeline_version') in ('source-spans-v5','source-spans-v6','source-spans-v7','source-spans-v8','source-spans-v9'):kinds+=('character_evidence',)
    for kind in kinds:
        api=rows(kind,page)
        query="SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='"+gen+"' AND kind='"+kind+"'"
        if snapshot_job['status']=='COMPLETED':
            if kind not in db_cache:db_cache[kind]=sql(query)
            db=[r for r in db_cache[kind] if r['data']['pdf_page']==page]
        else:db=sql(query+" AND data->>'pdf_page'='"+str(page)+"'")
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
        if c['speaker'] is not None:
            assert c['speaker_status']=='EXPLICIT_TEXT_ATTRIBUTION'
            assert c['source_gate']=='MATCH' and c['kind']=='STATEMENT'
            assert c['speaker_source_span_refs'] and c['visual_identity_verified'] is False
reviews=sql("SELECT count(*) FROM editor.reviews WHERE generation_id='"+gen+"'")
assert reviews==0 and not rows('visual_corrections')
job=get('/v1/jobs/'+run['job_id'])
if snapshot_job['status']=='COMPLETED':
    expected=set(range(1,job['source_coverage']['expected_pages']+1))
    assert set(r['data']['pdf_page'] for r in readings)==expected,'INCOMPLETE_SOURCE_PAGES'
    assert completed==expected,'INCOMPLETE_PAGE_CHECKS'
report={'generation_id':gen,'job_status':job['status'],'snapshot_job_status':snapshot_job['status'],'api':base,'checks':checks,
    'checked_at':datetime.now(timezone.utc).isoformat(),
    'old_visual_descriptions':0,'manual_reviews':0,'source_corrections':0,
    'semantic_acceptance':False,'counts':job['counts']}
(root/'evidence/source-spans-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
