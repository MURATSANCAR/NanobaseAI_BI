#!/usr/bin/env python3
"""Remote real API/PG integrity acceptance for derived identity and semantics.

This checks scope, immutable inputs and gates, not human literary correctness.
"""
import base64
import hashlib
import json
import os
import re
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
kinds = ('evidence', 'layout_regions', 'source_spans', 'page_claims', 'figure_identity', 'figure_comparisons',
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
def verify_reading_view(view,allowed_refs,page):
    refs=view['span_refs'];assert refs and len(set(refs))==len(refs) and set(refs)<=set(allowed_refs)
    assert all(spans[r]['status']=='TEXT_AGREED' and spans[r]['role']=='TEXT' and spans[r]['pdf_page']==page for r in refs)
    assert len({spans[r]['render_sha256'] for r in refs})==1
    assert view['raw_text']=='\n'.join(spans[r]['text'] for r in refs),'READING_RAW_TEXT_CHANGED'
    joins={(j['left_span_ref'],j['right_span_ref']):j for j in view['line_end_joins']}
    assert len(joins)==len(view['line_end_joins']) and set(joins)<=set(zip(refs,refs[1:]))
    text=spans[refs[0]]['text']
    for left,right in zip(refs,refs[1:]):
        a,b=spans[left],spans[right]
        if (left,right) in joins:
            x,y,w,h=a['bbox'];xx,yy,ww,hh=b['bbox']
            if joins[left,right]['operation']=='JOIN_VERIFIED_DROP_CAP_IN_READING_VIEW_ONLY':
                glyph=a['text'].strip();body=b['text'].lstrip()
                assert len(glyph)==1 and glyph.isalpha() and glyph.isupper() and body[0].islower()
                assert h>=1.4*hh and x<xx and -.5*w<=xx-(x+w)<=.15*hh
                assert max(0,min(y+h,yy+hh)-max(y,yy))>=.5*hh and y+h>yy+hh
                text=text.rstrip()+b['text'].lstrip()
            else:
                assert joins[left,right]['operation']=='REMOVE_GEOMETRIC_LINE_END_HYPHEN_IN_READING_VIEW_ONLY'
                assert re.search(r'\w-\s*$',a['text']) and re.match(r'^\s*\w',b['text'])
                assert yy>=y+.5*h and yy-(y+h)<=2*max(h,hh)
                assert max(0,min(x+w,xx+ww)-max(x,xx))>=.5*min(w,ww)
                text=re.sub(r'-\s*$','',text)+b['text'].lstrip()
        else:text+='\n'+b['text']
    assert text==view['reading_text'],'UNDECLARED_READING_TEXT_CHANGE'
for page in pages.values():
    if page.get('source_unit_method') not in ('source-unit-claims-v1','source-unit-claims-v2'):continue
    units=page.get('source_units',[]);lookup={u['unit_id']:u for u in units}
    assert len(lookup)==len(units),'SOURCE_UNIT_ID_COLLISION'
    for unit in units:
        refs=unit['span_refs'];assert refs and len(set(refs))==len(refs)
        assert all(spans[r]['status']=='TEXT_AGREED' and spans[r]['role']=='TEXT'
                   and spans[r]['pdf_page']==page['pdf_page'] and spans[r]['render_sha256']==unit['render_sha256'] for r in refs)
        assert unit['quote']=='\n'.join(spans[r]['text'] for r in refs),'SOURCE_UNIT_TEXT_MODIFIED'
        assert unit['sha256']==digest({k:unit[k] for k in ('pdf_page','span_refs','quote','render_sha256')})
        if page['source_unit_method']=='source-unit-claims-v2':
            assert unit['reading_view']['span_refs']==refs
            verify_reading_view(unit['reading_view'],refs,page['pdf_page'])
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
def verify_purpose(page,gate):
    assert extended,'PAGE_PURPOSE_REQUIRES_EXTENDED_VERIFICATION'
    contexts={r['id']:r['data'] for r in api['page_context_roles']}
    context=contexts[gate['record_id']]
    assert context['version']=='source-page-context-v4' and context['pdf_page']==page
    assert gate['record_sha256']==digest(context)
    layouts={r['data']['pdf_page']:r['data'] for r in api['layout_regions']}
    neighbours=[]
    for row in api['evidence']:
        n=row['data']['pdf_page']
        if abs(n-page)>1:continue
        regions=[]
        for span in api['source_spans']+api['source_fragments']:
            d=span['data']
            if d['pdf_page']!=n:continue
            agreed=d['status']=='TEXT_AGREED' and d['role']=='TEXT'
            regions.append({'ref':span['id'] if agreed else None,'can_cite':agreed,
                'text':d['text'] if agreed else '[UNVERIFIED_REGION]','bbox':d['bbox'],
                'is_verified_subregion':bool(agreed and d.get('parent_source_span_id'))})
        neighbours.append({'pdf_page':n,'regions':regions,
            'balloon_count':len(layouts[n].get('balloon_candidates',[])),
            'picture_count':sum(r.get('type')=='PICTURE' for r in layouts[n].get('regions',[]))})
    expected=digest({'target_page':page,'pages':neighbours})
    assert gate['input_sha256']==context['input_sha256']==expected,'PAGE_PURPOSE_SOURCE_HASH_MISMATCH'
    if gate['passed']:
        assert context['content_scope']==context['review']['content_scope']=='STORY_WORLD'
        assert context['eligible_for_identity_context'] and context['review']['supported']
        assert context['uncertainty_review_complete'] and context['blocking_uncertainties']==[]
        assert context['metrics']['finish_reason']==context['review_metrics']['finish_reason']=='stop'
for row in api['semantic_reviews']:
    review = row['data']; page = pages[review['pdf_page']]
    assert review['input_page_claims_sha256'] == digest(page), 'REVIEW_INPUT_MISMATCH'
    assert review['semantic_acceptance'] is False and review['source_records_modified'] is False
    candidates = page['claims']+page['blocked_claims']
    if review['version'] in ('source-semantic-review-v4','source-semantic-review-v5'):
        verify_purpose(review['pdf_page'],review['page_purpose_gate'])
    assert len(review['claims']) == len(candidates), 'REVIEW_COVERAGE_MISMATCH'
    for verdict in review['claims']:
        candidate = candidates[verdict['candidate_ordinal']]
        assert verdict['candidate_sha256'] == digest(candidate), 'CANDIDATE_HASH_MISMATCH'
        if verdict['eligible_for_synthesis']:
            if review['version'] in ('source-semantic-review-v4','source-semantic-review-v5'):assert review['page_purpose_gate']['passed']
            assert verdict['source_gate']=='MATCH' and verdict['status']=='MACHINE_SUPPORTED_CANDIDATE'
            assert all(value=='PASS' for value in verdict['model_result']['checks'].values())
            assert all(spans[ref]['status']=='TEXT_AGREED' and spans[ref]['pdf_page']==review['pdf_page'] for ref in candidate['span_refs'])
            assert verdict['identity_gate'] in ('NOT_REQUIRED','SOURCE_VERIFIED')
            assert verdict['claim_id'] not in eligible, 'CLAIM_ID_COLLISION'
            carried=candidate['span_refs']
            if review['version'] in ('source-semantic-review-v2','source-semantic-review-v3','source-semantic-review-v4','source-semantic-review-v5'):
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
                if review['version'] in ('source-semantic-review-v3','source-semantic-review-v4','source-semantic-review-v5'):
                    views=cited['source_reading_segments'];view_refs=[ref for view in views for ref in view['span_refs']]
                    assert len(view_refs)==len(set(view_refs)) and set(view_refs)==set(carried)
                    for view in views:verify_reading_view(view,carried,review['pdf_page'])
                    claim={k:candidate.get(k) for k in ('kind','text','quote','span_refs','actor','speaker','narrative_mode','polarity')}
                    assert cited['input_sha256']==digest({'claim':claim,'cited_source_regions':regions,'source_reading_segments':views})
            eligible[verdict['claim_id']] = {**candidate,'span_refs':carried}
for row in api['figure_identity']:
    identity = row['data']
    if identity['method']=='figure-identity-v2':verify_purpose(identity['pdf_page'],identity['page_purpose_gate'])
    assert identity['semantic_acceptance'] is False
    for link in identity['links']:
        assert link['eligible_for_synthesis'] is False
        if link['visual_identity_verified']:
            if identity['method']=='figure-identity-v2':assert identity['page_purpose_gate']['passed']
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
model_calls={}
def verify_attempts(value):
    if isinstance(value,list):
        for item in value:verify_attempts(item)
    elif isinstance(value,dict):
        if value.get('generation_retry_policy')=='LENGTH_ONLY_IDENTICAL_INPUT_ONCE_WITHIN_CONTEXT':
            attempts=value['generation_attempts']
            assert 1<=len(attempts)<=2,'UNBOUNDED_MODEL_RETRY'
            assert len({a['messages_sha256'] for a in attempts})==1,'MODEL_RETRY_INPUT_CHANGED'
            assert attempts[0]['max_output_tokens']==value['requested_max_output_tokens']
            assert attempts[-1]['finish_reason']==value['finish_reason']=='stop'
            assert attempts[-1]['request_sha256']==value['request_sha256']
            for attempt in attempts:
                assert attempt['max_output_tokens']+value['input_token_count']+512<=value['context_limit']
                assert re.fullmatch('[0-9a-f]{64}',attempt['response_sha256'])
                assert attempt['usage']['completion_tokens']<=attempt['max_output_tokens']
            if len(attempts)==2:
                assert attempts[0]['finish_reason']=='length','COMPLETED_VERDICT_RETRIED'
                assert attempts[0]['max_output_tokens']<attempts[1]['max_output_tokens']<=2*attempts[0]['max_output_tokens']
                assert isinstance(attempts[0]['incomplete_output'],str)
            model_calls[(value['started_at'],value['request_sha256'])]=len(attempts)
        for child in value.values():verify_attempts(child)
for items in api.values():
    for row in items:verify_attempts(row['data'])
report = {'generation_id':generation,'api':base,'api_pg_match':True,
          'counts':{kind:len(api[kind]) for kind in kinds},'eligible_claims':len(eligible),
          'bounded_model_calls_verified':len(model_calls),
          'length_retry_calls_verified':sum(n==2 for n in model_calls.values()),
          'derived_integrity_passed':True,'semantic_acceptance':False,'application_writes':0}
target = root/'evidence'/('source-analysis-'+generation+'.json')
target.write_text(json.dumps(report,indent=2));target.chmod(0o600)
print(json.dumps(report))
