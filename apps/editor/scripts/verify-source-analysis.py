#!/usr/bin/env python3
"""Remote real API/PG integrity acceptance for derived identity and semantics.

This checks scope, immutable inputs and gates, not human literary correctness.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid

root = Path(__file__).resolve().parents[1]
os.chdir(root)
generation = str(uuid.UUID(sys.argv[1]))
base = os.environ.get('EDITOR_VERIFY_BASE_URL', 'http://127.0.0.1:8810')
headers = {'Authorization': 'Bearer ' + (root/'secrets/api_token').read_text().strip()}
kinds = ('evidence', 'source_spans', 'page_claims', 'figure_identity', 'figure_comparisons',
         'semantic_reviews', 'semantic_synthesis')
def read(kind):
    rows = []
    while True:
        request = urllib.request.Request(f'{base}/v1/generations/{generation}/{kind}?limit=100&offset={len(rows)}', headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            batch = json.load(response)
        rows.extend(batch['items'])
        if not batch['has_more']:
            return rows
        assert batch['items'], 'EMPTY_PAGINATION'

api = {kind: read(kind) for kind in kinds}
code = '''import json,sys
from editor.config import connection
with connection() as db:
 rows=db.execute('SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s AND kind=ANY(%s)',(sys.argv[1],sys.argv[2:])).fetchall()
print(json.dumps(rows,default=str))
'''
database = json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,generation,*kinds]))
for kind in kinds:
    expected = {r['id']: {'id':r['id'],'record_key':r['record_key'],'data':r['data']} for r in database if r['kind']==kind}
    assert {r['id']:r for r in api[kind]} == expected, 'API_PG_MISMATCH:'+kind

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
pages = {r['data']['pdf_page']:r['data'] for r in api['page_claims']}
assert pages and api['semantic_reviews'] and api['figure_identity'], 'DERIVED_ANALYSIS_NOT_READY'
expected_pages = {r['data']['pdf_page'] for r in api['evidence']}
assert set(pages) == expected_pages, 'PAGE_CLAIMS_INCOMPLETE'
assert {r['data']['pdf_page'] for r in api['semantic_reviews']} == expected_pages, 'SEMANTIC_REVIEWS_INCOMPLETE'
assert {r['data']['pdf_page'] for r in api['figure_identity']} == expected_pages, 'IDENTITY_PASS_INCOMPLETE'
assert len(api['semantic_synthesis']) == 1, 'SYNTHESIS_NOT_READY'
spans = {r['id']:r['data'] for r in api['source_spans']}
eligible = {}
for row in api['semantic_reviews']:
    review = row['data']; page = pages[review['pdf_page']]
    assert review['input_page_claims_sha256'] == digest(page), 'REVIEW_INPUT_MISMATCH'
    assert review['semantic_acceptance'] is False and review['source_records_modified'] is False
    candidates = page['claims']+page['blocked_claims']
    assert len(review['claims']) == len(candidates), 'REVIEW_COVERAGE_MISMATCH'
    for verdict in review['claims']:
        candidate = candidates[verdict['candidate_ordinal']]
        assert verdict['candidate_sha256'] == digest(candidate), 'CANDIDATE_HASH_MISMATCH'
        if verdict['eligible_for_synthesis']:
            assert verdict['source_gate']=='MATCH' and verdict['status']=='MACHINE_SUPPORTED_CANDIDATE'
            assert all(value=='PASS' for value in verdict['model_result']['checks'].values())
            assert all(spans[ref]['status']=='TEXT_AGREED' and spans[ref]['pdf_page']==review['pdf_page'] for ref in candidate['span_refs'])
            assert verdict['identity_gate'] in ('NOT_REQUIRED','SOURCE_VERIFIED')
            assert verdict['claim_id'] not in eligible, 'CLAIM_ID_COLLISION'
            eligible[verdict['claim_id']] = candidate
for row in api['figure_identity']:
    identity = row['data']
    assert identity['semantic_acceptance'] is False
    for link in identity['links']:
        assert link['eligible_for_synthesis'] is False
        if link['visual_identity_verified']:
            assert {e['kind'] for e in link['identity_evidence']} == {'EXPLICIT_TEXT_ATTRIBUTION','UNIQUE_BALLOON_TAIL'}
            for evidence in link['identity_evidence']:
                for ref in evidence.get('source_span_refs',[]):
                    assert spans[ref]['status']=='TEXT_AGREED' and spans[ref]['pdf_page']==identity['pdf_page']
for row in api['figure_comparisons']:
    pair = row['data']
    assert pair['visual_identity_verified'] is False and pair['eligible_for_synthesis'] is False
    assert len(pair['crop_image_base64']) == len(pair['crop_sha256']) == 2
    for image, wanted in zip(pair['crop_image_base64'], pair['crop_sha256']):
        assert hashlib.sha256(base64.b64decode(image,validate=True)).hexdigest()==wanted, 'IDENTITY_CROP_MISMATCH'
for row in api['semantic_synthesis']:
    result = row['data']
    assert result['semantic_acceptance'] is False and result['complete_book'] is False
    assert result['input_claim_count']==len(eligible)
    for statement in result['statements']:
        assert statement['claim_refs'] and set(statement['claim_refs']) <= set(eligible)
        assert statement['verification']['supported'] is True
        expected_spans = {ref for cid in statement['claim_refs'] for ref in eligible[cid]['span_refs']}
        assert set(statement['source_span_refs'])==expected_spans
report = {'generation_id':generation,'api':base,'api_pg_match':True,
          'counts':{kind:len(api[kind]) for kind in kinds},'eligible_claims':len(eligible),
          'derived_integrity_passed':True,'semantic_acceptance':False,'application_writes':0}
target = root/'evidence'/('source-analysis-'+generation+'.json')
target.write_text(json.dumps(report,indent=2));target.chmod(0o600)
print(json.dumps(report))
