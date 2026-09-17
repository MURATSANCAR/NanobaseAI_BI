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


generation_row = sql(f"SELECT json_build_object('content_version_id',content_version_id,'manifest',manifest) FROM editor.generations WHERE id='{gen}'")
manifest = generation_row['manifest']
assert manifest['pipeline_version'] in ('source-spans-v6','source-spans-v7')
root_parent = str(uuid.UUID(manifest['reuse_measurements_from']))


def nearest_parent(page, key):
    current = root_parent; seen = set(); lineage = []
    for _ in range(64):
        assert current not in seen, 'ANCESTRY_CYCLE'
        seen.add(current)
        actual = get('/v1/generations/'+current)
        stored = sql(f"SELECT json_build_object('content_version_id',content_version_id,'manifest',manifest) FROM editor.generations WHERE id='{current}'")
        assert stored and stored['manifest']==actual['manifest']
        assert stored['content_version_id']==actual['content_version_id']==generation_row['content_version_id'], 'ANCESTRY_CONTENT_MISMATCH'
        present = []
        for kind in ('page_readings','layout_regions','visual_observations','page_claims','page_checks'):
            records = equal_rows(current,kind,page)
            assert len(records)<=1, 'DUPLICATE_PARENT_PAGE'
            if records:
                assert records[0]['record_key']==key and records[0]['data']['pdf_page']==page
                present.append(kind)
        lineage.append({'generation_id':current,'present_kinds':present})
        if len(present)==5:
            return current,lineage
        previous = stored['manifest'].get('reuse_measurements_from')
        if previous is None:
            return None,lineage
        current = str(uuid.UUID(previous))
    raise AssertionError('ANCESTRY_DEPTH_EXCEEDED')
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
    expected_parent,lineage = nearest_parent(page,frozen['record_key'])
    parent = frozen['data'].get('reused_from_generation')
    if manifest['pipeline_version']=='source-spans-v7':
        assert parent==expected_parent, 'NOT_NEAREST_COMPLETE_PAGE_PARENT'
    else:
        assert parent==root_parent, 'V6_DIRECT_PARENT_MISMATCH'
    if parent:
        parent_reading = equal_rows(parent,'page_readings',page)
        assert len(parent_reading)==1 and frozen['data']['reused_reading_id']==parent_reading[0]['id']
    evidence = equal_rows(gen,'evidence',page)
    assert len(evidence)==1 and frozen['data']['evidence_refs']==[evidence[0]['id']]
    if parent:
        previous_evidence = equal_rows(parent,'evidence',page)
        assert len(previous_evidence)==1
        for field in ('source_sha256','render_sha256','ocr_render_sha256','ocr_artifact_sha256'):
            assert evidence[0]['data'][field]==previous_evidence[0]['data'][field]
    spans = equal_rows(gen,'source_spans',page)
    parents = {r['record_key']: r for r in equal_rows(parent,'source_spans',page)} if parent else {}
    assert len(spans)==frozen['data']['span_count']
    if parent: assert {r['record_key'] for r in spans}==parents.keys()
    changed_context = False; regional = 0
    for row in spans:
        d = row['data']; old = parents.get(row['record_key'])
        assert d['evidence_refs']==[evidence[0]['id']] and d['pdf_page']==page
        if old:
            for field in immutable_fields:
                assert d[field] == old['data'][field], 'RAW_MEASUREMENT_CHANGED:'+field+':'+row['id']
            assert d['reused_source_span_id'] == old['id'] and d['reused_from_generation'] == parent
        else:
            assert d.get('reused_source_span_id') is None and d.get('reused_from_generation') is None
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
        old_agreed = old is not None and old['data']['status']=='TEXT_AGREED'; agreed = d['status']=='TEXT_AGREED'
        counts['agreed' if agreed else 'review'] += 1
        if old and agreed and not old_agreed: promoted.append({'id':row['id'],'parent_id':old['id'],'key':row['record_key'],'pdf_page':page})
        if old_agreed and not agreed: demoted.append({'id':row['id'],'parent_id':old['id'],'key':row['record_key'],'pdf_page':page})
        changed_context |= old is None or d['text'] != old['data']['text'] or agreed and not old_agreed
    assert sum(r['data']['status']=='TEXT_AGREED' for r in spans) == frozen['data']['agreed_spans']
    assert sum(r['data']['status']!='TEXT_AGREED' for r in spans) == frozen['data']['review_spans']
    # Only inspect claims after their page_checks commit; source processing may
    # already be complete while that same page's new model call is still running.
    claims_checked = page in completed_claim_pages
    if claims_checked:
        claims = equal_rows(gen,'page_claims',page)
        assert len(claims) == 1
        if changed_context: assert claims[0]['data']['reused_claim_candidates_from'] is None, 'CHANGED_CONTEXT_REUSED'
        reused_claim = claims[0]['data'].get('reused_claim_candidates_from')
        if reused_claim:
            previous_claims = equal_rows(parent,'page_claims',page)
            assert len(previous_claims)==1 and reused_claim==previous_claims[0]['id']
            assert claims[0]['data']['reused_from_generation']==parent
        visuals = equal_rows(gen,'visual_observations',page)
        assert len(visuals)==1
        if visuals[0]['data'].get('reused_visual_observation_id'):
            previous_visual = equal_rows(parent,'visual_observations',page)
            assert len(previous_visual)==1
            assert visuals[0]['data']['reused_visual_observation_id']==previous_visual[0]['id']
            assert visuals[0]['data']['reused_from_generation']==parent
            assert set(visuals[0]['data']['source_span_ids'])=={r['id'] for r in spans}
        assert all(c['eligible_for_synthesis'] is False for key in ('claims','blocked_claims') for c in claims[0]['data'][key])
    assert equal_rows(gen,'source_spans',page) == spans, 'IMMUTABLE_PAGE_CHANGED'
    pages.append({'pdf_page':page,'spans':len(spans),'regional_selections':regional,
                  'context_changed':changed_context,'claims_checked':claims_checked,'api_pg_equal':True,
                  'selected_parent_generation_id':parent,'nearest_complete_parent':expected_parent,'lineage':lineage})
reviews = sql(f"SELECT count(*) FROM editor.reviews WHERE generation_id='{gen}'")
assert reviews == 0
job_status = get('/v1/jobs/'+job)
report = {'generation_id':gen,'parent_generation_id':root_parent,'api':base,'job_status':job_status['status'],
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
