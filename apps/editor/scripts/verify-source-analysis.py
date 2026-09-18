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
extended = '--fragments' in sys.argv
if extended:
    kinds += ('source_fragments','fragment_checks','page_context_roles','cross_page_attributions')
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
for page in pages.values():
    if page.get('source_unit_method')!='source-unit-claims-v1':continue
    units=page.get('source_units',[]);lookup={u['unit_id']:u for u in units}
    assert len(lookup)==len(units),'SOURCE_UNIT_ID_COLLISION'
    for unit in units:
        refs=unit['span_refs'];assert refs and len(set(refs))==len(refs)
        assert all(spans[r]['status']=='TEXT_AGREED' and spans[r]['role']=='TEXT'
                   and spans[r]['pdf_page']==page['pdf_page'] and spans[r]['render_sha256']==unit['render_sha256'] for r in refs)
        assert unit['quote']=='\n'.join(spans[r]['text'] for r in refs),'SOURCE_UNIT_TEXT_MODIFIED'
        assert unit['sha256']==digest({k:unit[k] for k in ('pdf_page','span_refs','quote','render_sha256')})
    for claim in page['claims']+page['blocked_claims']:
        unit=lookup[claim['source_unit_id']]
        assert claim['quote_origin']=='IMMUTABLE_OCR_UNIT_SELECTION'
        assert claim['quote']==unit['quote'] and claim['span_refs']==unit['span_refs']
        assert claim['source_unit_sha256']==unit['sha256']
        assert claim['text']==claim['model_candidate']['text'],'MODEL_CLAIM_TEXT_CHANGED'
if extended:
    assert {r['data']['pdf_page'] for r in api['fragment_checks']} == expected_pages, 'FRAGMENT_CHECKS_INCOMPLETE'
    for row in api['source_fragments']:
        fragment=row['data']; parent=spans[fragment['parent_source_span_id']]
        assert digest(parent)==fragment['parent_record_sha256'], 'FRAGMENT_PARENT_HASH_MISMATCH'
        assert fragment['parent_generation_id']==generation and parent['status']=='NEEDS_REVIEW'
        assert fragment['pdf_page']==parent['pdf_page'] and fragment['render_sha256']==parent['render_sha256']
        x,y,w,h=fragment['bbox'];px,py,pw,ph=parent['bbox']
        assert px<=x and py<=y and x+w<=px+pw+1e-9 and y+h<=py+ph+1e-9
        proof=fragment['measurement']
        assert hashlib.sha256(base64.b64decode(proof['crop_image_base64'],validate=True)).hexdigest()==proof['crop_sha256']
        assert hashlib.sha256(proof['paddle_raw_response'].encode()).hexdigest()==proof['paddle_response_sha256']
        for reading in proof['readings']:
            assert hashlib.sha256(reading['raw_tsv'].encode()).hexdigest()==reading['tsv_sha256']
        if fragment['status']=='TEXT_AGREED':
            assert not proof['blockers'] and proof['selected_text_is_unmodified_reader_output']
            if fragment['selected_reader']=='TESSERACT_PSM7_FRAGMENT':
                assert fragment['text']==proof['readings'][0]['text']
                assert hashlib.sha256(proof['vl_raw_response'].encode()).hexdigest()==proof['vl_response_sha256']
            else:
                assert fragment['selected_reader']=='PPOCR_FRAGMENT', 'UNKNOWN_FRAGMENT_READER'
                raw=json.loads(proof['paddle_raw_response'])
                assert raw['image_sha256']==proof['crop_sha256']
                ordered=sorted(raw['lines'],key=lambda line:(min(p[1] for p in line['polygon']),min(p[0] for p in line['polygon'])))
                assert fragment['text']==' '.join(line['text'] for line in ordered), 'FRAGMENT_RAW_READER_MISMATCH'
        assert fragment['eligible_for_synthesis'] is False and fragment['visual_identity_verified'] is False
    assert len(api['cross_page_attributions'])==1, 'CROSS_PAGE_PASS_INCOMPLETE'
    links=api['cross_page_attributions'][0]['data']
    assert links['source_page_coverage_complete'] and not links['scope_errors']
    for link in links['links']:
        assert link['eligible_for_synthesis'] is False
        if link.get('dialogue_link_verified'):
            assert link['identity_evidence'] and link.get('speaker')
            assert not link.get('semantic_acceptance', False)
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
            carried=candidate['span_refs']
            if review['version']=='source-semantic-review-v2':
                carried=verdict['verified_support_span_refs']
                assert set(candidate['span_refs'])<=set(carried)
                assert set(verdict['model_result']['support_span_refs'])<=set(carried)
                assert all(spans[r]['status']=='TEXT_AGREED' and spans[r]['role']=='TEXT'
                           and spans[r]['pdf_page']==review['pdf_page'] for r in carried)
                regions=[{'span_id':ref,**{k:spans[ref][k] for k in ('text','bbox','render_sha256')}} for ref in carried]
                assert verdict['verified_support_regions']==regions
                cited=verdict['citation_review'];assert cited['passed'] is True
                assert cited['source_sha256']==digest(regions)
                assert all(v=='PASS' for v in cited['model_result']['checks'].values())
            eligible[verdict['claim_id']] = {**candidate,'span_refs':carried}
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
