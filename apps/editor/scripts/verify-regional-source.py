#!/usr/bin/env python3
"""Read-only API/PG acceptance at a frozen completed optical-page boundary."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import unicodedata
import urllib.request
import uuid

root = Path(os.environ.get('EDITOR_VERIFY_ROOT', Path(__file__).resolve().parents[1]))
os.chdir(root)
run = json.loads(Path(os.environ['EDITOR_VERIFY_RUN_FILE']).read_text())
gen = str(uuid.UUID(run['generation_id'])); job = str(uuid.UUID(run['job_id']))
base = os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/')
headers = {'Authorization': 'Bearer '+(root/'secrets/api_token').read_text().strip()}


def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path, headers=headers), timeout=60) as response:
        return json.load(response)


def sql(query):
    return json.loads(subprocess.check_output(['docker', 'compose', 'exec', '-T', 'postgres',
        'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query], text=True))


def api_rows(generation, kind, page=None):
    result = []
    while True:
        batch = get(f'/v1/generations/{generation}/{kind}?offset={len(result)}&limit=100'
                    +(f'&pdf_page={page}' if page is not None else ''))
        result.extend(batch['items'])
        if not batch['has_more']:
            return result
        assert batch['items'], 'EMPTY_PAGINATION'


def equal_rows(generation, kind, page):
    actual = api_rows(generation, kind, page)
    reference = sql("SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) "
        f"ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='{generation}' "
        f"AND kind='{kind}' AND data->>'pdf_page'='{int(page)}'")
    assert actual == reference, f'API_PG_MISMATCH:{kind}:{page}'
    return actual


def tokens(text):
    return re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', text).replace('İ','i').replace('I','ı').lower())


def clean(text):
    return all(unicodedata.category(c) not in ('Co','Cs') and c != '\ufffd' for c in text)


def text_hash(text):
    return hashlib.sha256(text.encode('utf-8', errors='surrogatepass')).hexdigest()


def reference(data):
    region = data.get('region_text') or ''; candidate = tokens(region)
    secondary = tokens(data['secondary_text']); native = tokens(data['pdf_text'])
    support = []
    if secondary and secondary == candidate and clean(data['secondary_text']): support.append('TESSERACT')
    if data['pdf_usable'] and native and native == candidate and clean(data['pdf_text']): support.append('NATIVE_PDF')
    conflict = ((bool(secondary) or not clean(data['secondary_text'])) and 'TESSERACT' not in support
                or data['pdf_usable'] and 'NATIVE_PDF' not in support)
    reread = data.get('reread_measurement'); state = 'NOT_AVAILABLE'
    if reread:
        readers = reread['readings']
        assert len(readers) == 2 and [r['psm'] for r in readers] == [7,13]
        a,b = [tokens(r['text']) for r in readers]
        state = ('AGREES' if a == candidate and all(clean(r['text']) for r in readers) else 'DISAGREES') if a and a == b else 'UNSTABLE'
    score = data.get('region_score')
    valid_score = isinstance(score,(int,float)) and not isinstance(score,bool) and math.isfinite(score) and .9 <= score <= 1
    return bool(candidate and clean(region) and valid_score and support and not conflict and state != 'DISAGREES'), support, state


manifest = sql(f"SELECT manifest FROM editor.generations WHERE id='{gen}'")
assert manifest['pipeline_version'] == 'source-spans-v6'
parent = str(uuid.UUID(manifest['reuse_measurements_from']))
# page_readings is committed after all optical spans. Freeze only these pages;
# never compare global row counts while the next page is being written.
boundary = {r['data']['pdf_page']: r for r in api_rows(gen,'page_readings')}
assert boundary, 'NO_COMPLETED_OPTICAL_PAGES'
completed_claim_pages = {r['data']['pdf_page'] for r in api_rows(gen,'page_checks')}
counts = Counter(); pages = []; promoted = []; demoted = []
immutable_fields = ('raw_text','bbox','region_text','region_score','secondary_text','pdf_text','pdf_usable',
    'secondary_word_regions','pdf_word_regions','score','render_sha256','model_manifest','reread_measurement')
for page, frozen in sorted(boundary.items()):
    reading_rows = equal_rows(gen,'page_readings',page)
    assert reading_rows == [frozen], 'COMPLETED_READING_CHANGED'
    spans = equal_rows(gen,'source_spans',page)
    parents = {r['record_key']: r for r in equal_rows(parent,'source_spans',page)}
    assert len(spans) == len(parents) == frozen['data']['span_count']
    changed_context = False; regional = 0
    for row in spans:
        d = row['data']; old = parents[row['record_key']]
        for field in immutable_fields:
            assert d[field] == old['data'][field], 'RAW_MEASUREMENT_CHANGED:'+field+':'+row['id']
        assert d['reused_source_span_id'] == old['id'] and d['reused_from_generation'] == parent
        supported, readers, reread_state = reference(d)
        selection = d['regional_selection']
        assert (selection['status']=='SUPPORTED_REGIONAL_CANDIDATE') == supported
        assert selection['selected_text'] == (d['region_text'] if supported else None)
        assert selection['raw_full_page_text'] == d['raw_text']
        assert selection['supporting_readers'] == readers and selection['reread_state'] == reread_state
        assert selection['eligible_for_synthesis'] is False and selection['visual_identity_verified'] is False
        for name, value in [('full_page_text_sha256',d['raw_text']),('region_text_sha256',d['region_text'] or ''),
                            ('secondary_text_sha256',d['secondary_text']),('pdf_text_sha256',d['pdf_text'])]:
            assert selection['provenance'][name] == text_hash(value)
        assert selection['provenance']['region_score'] == d['region_score']
        assert selection['provenance']['pdf_usable'] == d['pdf_usable']
        expected_hashes = [{'psm':r['psm'],'text_sha256':text_hash(r['text'])} for r in (d.get('reread_measurement') or {}).get('readings',[])]
        assert selection['provenance']['reread_text_hashes'] == expected_hashes
        if d['selected_reader'] == 'REGIONAL_OCR':
            assert supported and d['text'] == d['region_text'] and d['status'] == 'TEXT_AGREED'
            assert d['issues'] == ['FULL_PAGE_READING_SUPERSEDED']
            regional += 1
        else:
            assert d['selected_reader'] == 'FULL_PAGE_OCR' and d['text'] == d['raw_text']
        old_agreed = old['data']['status']=='TEXT_AGREED'; agreed = d['status']=='TEXT_AGREED'
        counts['agreed' if agreed else 'review'] += 1
        if agreed and not old_agreed: promoted.append({'id':row['id'],'parent_id':old['id'],'key':row['record_key'],'pdf_page':page})
        if old_agreed and not agreed: demoted.append({'id':row['id'],'parent_id':old['id'],'key':row['record_key'],'pdf_page':page})
        changed_context |= d['text'] != old['data']['text'] or agreed and not old_agreed
    assert sum(r['data']['status']=='TEXT_AGREED' for r in spans) == frozen['data']['agreed_spans']
    assert sum(r['data']['status']!='TEXT_AGREED' for r in spans) == frozen['data']['review_spans']
    # Only inspect claims after their page_checks commit; source processing may
    # already be complete while that same page's new model call is still running.
    claims_checked = page in completed_claim_pages
    if claims_checked:
        claims = equal_rows(gen,'page_claims',page)
        assert len(claims) == 1
        if changed_context: assert claims[0]['data']['reused_claim_candidates_from'] is None, 'CHANGED_CONTEXT_REUSED'
        assert all(c['eligible_for_synthesis'] is False for key in ('claims','blocked_claims') for c in claims[0]['data'][key])
    assert equal_rows(gen,'source_spans',page) == spans, 'IMMUTABLE_PAGE_CHANGED'
    pages.append({'pdf_page':page,'spans':len(spans),'regional_selections':regional,
                  'context_changed':changed_context,'claims_checked':claims_checked,'api_pg_equal':True})
reviews = sql(f"SELECT count(*) FROM editor.reviews WHERE generation_id='{gen}'")
assert reviews == 0
job_status = get('/v1/jobs/'+job)
report = {'generation_id':gen,'parent_generation_id':parent,'api':base,'job_status':job_status['status'],
          'frozen_optical_pages':len(boundary),'pages':pages,'counts':dict(counts),'promoted':promoted,'demoted':demoted,
          'manual_reviews':reviews,'source_or_review_writes':0,'semantic_acceptance':False,
          'complete_generation_coverage':len(boundary)==job_status['source_coverage']['expected_pages'],
          'at':datetime.now(timezone.utc).isoformat(),'verifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'frozen_source_checks':'PASS',
          'status':'PASS' if job_status['status']=='COMPLETED' and len(boundary)==job_status['source_coverage']['expected_pages'] else 'PARTIAL_VERIFIED',
          'end_to_end_job_success':job_status['status']=='COMPLETED'}
destination = root/'evidence'/('regional-source-verification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
destination.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({**report,'evidence':str(destination)},ensure_ascii=False,indent=2))
