#!/usr/bin/env python3
"""Real API/PG regression: lexical boundaries must survive optical comparison."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid

root = Path(__file__).resolve().parents[1]
os.chdir(root)
generation = str(uuid.UUID(json.loads((root/os.environ.get('EDITOR_VERIFY_RUN_FILE','evidence/source-spans-run.json')).read_text())['generation_id']))
headers = {'Authorization': 'Bearer '+(root/'secrets/api_token').read_text().strip()}
rows = []
while True:
    request = urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}/source_spans?offset={len(rows)}&limit=100', headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        batch = json.load(response)
    rows.extend(batch['items'])
    if not batch['has_more']:
        break
    assert batch['items'], 'EMPTY_PAGE'
query = f"SELECT json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key) FROM editor.records WHERE generation_id='{generation}' AND kind='source_spans'"
def database():
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query], text=True))
assert rows == database(), 'API_DB_MISMATCH'
code = '''import json,sys
from editor.source_pipeline import optical_verdict,VERSION,reusable_claim_candidates
from editor.book_store import get_records
rows=json.load(sys.stdin)
verdicts=[optical_verdict(r['data'],r['data']['secondary_text'],r['data']['pdf_text'],r['data']['pdf_usable'],r['data'].get('reread_measurement')) for r in rows]
predicted=[{**r,'data':{**r['data'],'status':v['status'],'issues':v['issues']}} for r,v in zip(rows,verdicts)]
reuse=[]
for page in get_records(sys.argv[1],'page_claims'):
 spans=[r for r in predicted if r['data']['pdf_page']==page['data']['pdf_page']]
 result=reusable_claim_candidates(sys.argv[1],page['record_key'],spans)
 assert result is not None, 'UNCHANGED_OR_STRICTER_CONTEXT_NOT_REUSED'
 assert all(c['eligible_for_synthesis'] is False for c in result[0]['claims'])
 reuse.append({'page':page['data']['pdf_page'],'policy':result[0]['measurement_reuse_policy']})
promotion_rejections=[]
if len(sys.argv)>2:
 baseline=sys.argv[2];old={r['record_key']:r for r in get_records(baseline,'source_spans')}
 for page in get_records(baseline,'page_claims'):
  spans=[r for r in rows if r['data']['pdf_page']==page['data']['pdf_page']]
  promoted=[r for r in spans if r['record_key'] in old and r['data']['status']=='TEXT_AGREED' and old[r['record_key']]['data']['status']!='TEXT_AGREED']
  if promoted:
   assert reusable_claim_candidates(baseline,page['record_key'],spans) is None, 'PROMOTED_CONTEXT_REUSED'
   promotion_rejections.append(page['data']['pdf_page'])
 assert promotion_rejections, 'NO_REAL_PROMOTION_CASES'
print(json.dumps({'version':VERSION,'verdicts':verdicts,'candidate_reuse':reuse,'real_promotion_rejections':promotion_rejections}))
'''
candidate = os.environ.get('EDITOR_BOUNDARY_CANDIDATE')
if candidate:
    command = ['docker','compose','run','--rm','--no-deps','-T','-v',
        str(Path(candidate).resolve(strict=True))+':/app/editor/source_pipeline.py:ro',
        '--entrypoint','python','api','-c',code,generation]
else:
    command = ['docker','compose','exec','-T','api','python','-c',code,generation]
if os.environ.get('EDITOR_REUSE_BASELINE'):
    command.append(str(uuid.UUID(os.environ['EDITOR_REUSE_BASELINE'])))
result = json.loads(subprocess.check_output(command,input=json.dumps(rows),text=True))
assert len(result['verdicts']) == len(rows)
# Independent lexical reference: scan Unicode letters/numbers into runs.
# Do not call the application's normalization or tokenization helpers.
import unicodedata
import re
def tokens(value):
    value = re.sub(r'-\s*\n\s*', '', value)
    value = unicodedata.normalize('NFKC',value).replace('İ','i').replace('I','ı').lower()
    runs=[]; word=''
    for char in value:
        if char.isalnum():
            word += char
        elif word:
            runs.append(word); word=''
    if word: runs.append(word)
    return runs
changes=[]; old_agreed=0; new_agreed=0
for row, verdict in zip(rows,result['verdicts']):
    d=row['data']; old_agreed += d['status']=='TEXT_AGREED'; new_agreed += verdict['status']=='TEXT_AGREED'
    a=tokens(d['text']); b=tokens(d.get('region_text') or '')
    c=tokens(d['secondary_text']); p=tokens(d['pdf_text'])
    if verdict['status']=='TEXT_AGREED':
        assert a and a==b, 'REGIONAL_BOUNDARIES_LOST'
        assert (c==a or (d['pdf_usable'] and p==a)), 'NO_INDEPENDENT_READER'
        assert not c or c==a, 'SECONDARY_BOUNDARIES_LOST'
        assert not d['pdf_usable'] or p==a, 'PDF_BOUNDARIES_LOST'
    if verdict['status'] != d['status']:
        assert verdict['status']=='NEEDS_REVIEW', 'UNEXPECTED_PROMOTION'
        changes.append({'id':row['id'],'page':d['pdf_page'],'before':d['status'],'after':verdict['status'],'issues':verdict['issues']})
assert rows==database(), 'SOURCE_RECORDS_CHANGED'
report={'generation_id':generation,'version':result['version'],'api_pg_equal':True,'source_records_unchanged':True,
    'candidate_reuse':result['candidate_reuse'],
    'real_promotion_rejections':result['real_promotion_rejections'],
    'regions':len(rows),'old_agreed':old_agreed,'new_agreed':new_agreed,'review':len(rows)-new_agreed,
    'changes':changes,'semantic_acceptance':False,'candidate':bool(candidate),
    'code_sha256':hashlib.sha256(Path(candidate or root/'backend/editor/source_pipeline.py').read_bytes()).hexdigest()}
request=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}',headers=headers)
with urllib.request.urlopen(request,timeout=60) as response:
    metadata=json.load(response)
if metadata['manifest']['pipeline_version']=='source-spans-v4':
    assert metadata['status']=='NEEDS_REVIEW', 'GENERATION_NOT_FINISHED'
    assert not changes, 'STORED_VERDICTS_DIFFER_FROM_DEPLOYED_CODE'
    parent=str(uuid.UUID(metadata['manifest']['reuse_measurements_from']))
    parent_query=query.replace(generation,parent)
    previous=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',parent_query],text=True))
    by_id={row['id']:row for row in previous}
    assert len(rows)==len(previous), 'REGION_COUNT_CHANGED'
    changed=[]
    for row in rows:
        d=row['data']; old=by_id[d['reused_source_span_id']]['data']
        assert d['reused_from_generation']==parent
        for field in ('text','raw_text','bbox','region_text','region_score','score','secondary_text','pdf_text','render_sha256','reread_measurement'):
            assert d[field]==old[field], 'RAW_MEASUREMENT_CHANGED:'+field
        if d['status']!=old['status']:
            changed.append(d['reused_source_span_id'])
    expected=json.loads((root/'evidence/word-boundaries-candidate.json').read_text())
    assert expected['generation_id']==parent
    assert sorted(changed)==sorted(row['id'] for row in expected['changes']), 'UNEXPECTED_GATE_CHANGES'
    claims=[]
    while True:
        request=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}/page_claims?offset={len(claims)}&limit=100',headers=headers)
        with urllib.request.urlopen(request,timeout=60) as response:
            batch=json.load(response)
        claims.extend(batch['items'])
        if not batch['has_more']: break
        assert batch['items'], 'EMPTY_CLAIM_PAGE'
    claim_query=query.replace("kind='source_spans'", "kind='page_claims'")
    reference=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',claim_query],text=True))
    assert claims==reference, 'CLAIM_API_DB_MISMATCH'
    assert len(claims)==len({r['data']['pdf_page'] for r in rows}), 'MISSING_CLAIM_PAGES'
    sources={r['id']:r['data'] for r in rows};strict_pages=[]
    for row in claims:
        d=row['data']
        assert d['reused_claim_candidates_from'] and d['reused_from_generation']==parent
        if d['candidate_reuse_policy']=='UNCHANGED_MEASUREMENTS_STRICTER_SOURCE_GATE':
            strict_pages.append(d['pdf_page'])
        else:
            assert d['candidate_reuse_policy']=='IDENTICAL_CONTEXT'
        for claim in d['claims']+d['blocked_claims']:
            assert claim['eligible_for_synthesis'] is False and claim['speaker'] is None
            if claim['source_gate']=='MATCH':
                assert claim['span_refs'] and all(sources[ref]['status']=='TEXT_AGREED' for ref in claim['span_refs']), 'INVALIDATED_SOURCE_REACHED_MATCH'
    assert sorted(strict_pages)==sorted({r['page'] for r in expected['changes']}), 'WRONG_REUSE_POLICY'
    report['new_generation_acceptance']={'parent':parent,'raw_measurements_unchanged':True,
        'expected_gate_changes':len(changed),'stored_verdicts_equal':True,
        'reused_candidate_pages':len(claims),'strict_context_pages':strict_pages,
        'invalidated_source_match_count':0,'fresh_candidate_model_calls':0}
name='word-boundaries-candidate.json' if candidate else 'word-boundaries-deployed.json'
(root/'evidence'/name).write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
