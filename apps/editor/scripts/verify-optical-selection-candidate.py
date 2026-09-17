#!/usr/bin/env python3
"""Evaluate candidate code in the live API container without installing it.

Only GET and SELECT read actual source records; output is a separate evidence
artifact, never a source correction or editorial acceptance.
"""
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
generation = str(uuid.UUID(run['generation_id']))
job = str(uuid.UUID(run['job_id']))
base = os.environ.get('EDITOR_VERIFY_BASE_URL', 'http://127.0.0.1:8810').rstrip('/')
source_code = Path(os.environ['EDITOR_VERIFY_CANDIDATE_CODE']).read_text()
headers = {'Authorization': 'Bearer '+(root/'secrets/api_token').read_text().strip()}


def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path, headers=headers), timeout=60) as response:
        return json.load(response)


def database_rows():
    query = ("SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) "
             f"ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='{generation}' AND kind='source_spans'")
    return json.loads(subprocess.check_output(['docker', 'compose', 'exec', '-T', 'postgres',
        'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query], text=True))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def words(text):
    value = unicodedata.normalize('NFKC', text).replace('İ', 'i').replace('I', 'ı').lower()
    return re.findall(r'[^\W_]+', value)


def clean(text):
    return all(unicodedata.category(c) not in ('Co', 'Cs') and c != '\ufffd' for c in text)


def independent_reference(data, allow_crop_supersession=True):
    region = data.get('region_text') or ''
    crop = words(region)
    secondary = words(data['secondary_text']); native = words(data['pdf_text'])
    agreements = []
    if secondary and secondary == crop and clean(data['secondary_text']):
        agreements.append('TESSERACT')
    if data['pdf_usable'] and native and native == crop and clean(data['pdf_text']):
        agreements.append('NATIVE_PDF')
    conflicts = ((bool(secondary) or not clean(data['secondary_text'])) and 'TESSERACT' not in agreements
                 or data['pdf_usable'] and 'NATIVE_PDF' not in agreements)
    reread = data.get('reread_measurement')
    stable_conflict = False
    stable_region = False
    crop_scoped = False
    if reread:
        raw = reread['readings']
        assert len(raw) == 2 and [r['psm'] for r in raw] == [7, 13]
        first, second = [words(r['text']) for r in raw]
        stable_conflict = bool(first) and first == second and (first != crop or not all(clean(r['text']) for r in raw))
        stable_region = bool(first) and first == second == crop and all(clean(r['text']) for r in raw)
        crop_scoped = (reread.get('bbox') == data.get('bbox') and isinstance(data.get('bbox'), list)
                       and re.fullmatch('[0-9a-f]{64}', reread.get('crop_sha256') or '') is not None
                       and all(re.fullmatch('[0-9a-f]{64}', r.get('tsv_sha256') or '') is not None for r in raw))
    score = data.get('region_score')
    valid_score = isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score) and .9 <= score <= 1
    superseded = (bool(secondary) and 'TESSERACT' not in agreements and clean(data['secondary_text'])
                  and 'NATIVE_PDF' in agreements and stable_region and crop_scoped and valid_score and clean(region))
    if superseded and allow_crop_supersession:
        conflicts = False
        agreements.insert(0, 'TESSERACT_CROP')
    return bool(crop and clean(region) and valid_score and agreements and not conflicts and not stable_conflict), agreements


status = get('/v1/jobs/'+job)
assert status['status'] == 'COMPLETED', 'USE_COMPLETED_PARENT_GENERATION'
api = []
while True:
    batch = get(f'/v1/generations/{generation}/source_spans?offset={len(api)}&limit=100')
    api.extend(batch['items'])
    if not batch['has_more']:
        break
    assert batch['items'], 'EMPTY_PAGINATION'
before = database_rows()
assert api == before and api, 'API_PG_MISMATCH_OR_EMPTY'
# Execute the submitted file bytes inside the real running API container. No
# production module is copied/replaced and the submitted module has no DB code.
payload = {'source': source_code, 'rows': api}
runner = '''import json,sys,hashlib
payload=json.loads(sys.stdin.read())
namespace={}
exec(compile(payload['source'], '<optical-selection-candidate>', 'exec'), namespace)
output=[]
for row in payload['rows']:
 d=row['data']
 result=namespace['select_regional_candidate'](d,d['secondary_text'],d['pdf_text'],d['pdf_usable'],d.get('reread_measurement'))
 output.append({'id':row['id'],'selection':result})
print(json.dumps({'code_sha256':hashlib.sha256(payload['source'].encode()).hexdigest(),'results':output},ensure_ascii=True))
'''
executed = json.loads(subprocess.check_output(['docker', 'compose', 'exec', '-T', 'api', 'python', '-c', runner],
    input=json.dumps(payload, ensure_ascii=True), text=True))
assert executed['code_sha256'] == hashlib.sha256(source_code.encode()).hexdigest()
assert len(executed['results']) == len(api)
counts = Counter(); promoted = []; demoted = []; evidence = []
for row, candidate in zip(api, executed['results']):
    assert row['id'] == candidate['id']
    data = row['data']; selection = candidate['selection']
    reference, readers = independent_reference(data)
    previous_reference, _ = independent_reference(data, allow_crop_supersession=False)
    supported = selection['status'] == 'SUPPORTED_REGIONAL_CANDIDATE'
    assert supported == reference, 'INDEPENDENT_SELECTION_MISMATCH:'+row['id']
    assert not previous_reference or supported, 'PREVIOUS_POLICY_SUPPORT_LOST:'+row['id']
    assert selection['supporting_readers'] == readers
    superseded = 'TESSERACT_CROP' in readers
    assert selection['superseded_readers'] == (['FULL_PAGE_TESSERACT_SUPERSEDED'] if superseded else [])
    assert selection['raw_secondary_text'] == data['secondary_text']
    assert selection['raw_full_page_text'] == data['text'] == data['raw_text']
    assert selection['selected_text'] == (data['region_text'] if reference else None)
    assert selection['eligible_for_synthesis'] is False and selection['visual_identity_verified'] is False
    for field, raw in [('full_page_text_sha256', data['text']), ('region_text_sha256', data.get('region_text') or ''),
                       ('secondary_text_sha256', data['secondary_text']), ('pdf_text_sha256', data['pdf_text'])]:
        assert selection['provenance'][field] == hashlib.sha256(raw.encode('utf-8', errors='surrogatepass')).hexdigest()
    old_agreed = data['status'] == 'TEXT_AGREED'
    if previous_reference and not old_agreed:
        counts['previous_policy_review_improvements_preserved'] += 1
    counts['old_agreed' if old_agreed else 'old_review'] += 1
    counts['candidate_agreed' if supported else 'candidate_review'] += 1
    if superseded:
        counts['full_page_tesseract_superseded'] += 1
    item = {'id': row['id'], 'record_key': row['record_key'], 'pdf_page': data['pdf_page'],
            'literal_region_differs': data['text'] != data.get('region_text'),
            'word_tokens_differ': words(data['text']) != words(data.get('region_text') or '')}
    if supported and not old_agreed:
        promoted.append(item)
    if old_agreed and not supported:
        demoted.append(item)
    evidence.append({'source_record': row, 'candidate_selection': selection})
after = database_rows()
assert before == after, 'SOURCE_RECORDS_CHANGED_DURING_MEASUREMENT'
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
report = {'generation_id': generation, 'api': base, 'execution': 'live API container, submitted code only',
          'at': stamp, 'candidate_code_sha256': executed['code_sha256'], 'source_records_sha256': digest(before),
          'total_spans': len(api), 'api_pg_equal': True, 'independent_reference_equal': True,
          'source_records_unchanged': True, 'counts': dict(counts), 'promoted': promoted, 'demoted': demoted,
          'source_or_review_writes': 0, 'semantic_acceptance': False, 'production_installed': False,
          'measurements': evidence}
destination = root/'evidence'/('optical-selection-candidate-'+stamp+'.json')
destination.write_text(json.dumps(report, ensure_ascii=True, indent=2))
print(json.dumps({key: value for key, value in report.items() if key != 'measurements'} | {'evidence': str(destination)}, indent=2))
