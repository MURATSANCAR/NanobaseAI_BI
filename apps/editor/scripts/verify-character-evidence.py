#!/usr/bin/env python3
"""Read-only real API/PG checks; no production attribution function is imported.

This verifies retained literal provenance and conservative speaker links, not
character identity or semantic acceptance. Run on the connected installation.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata
import urllib.request
import uuid

root = Path(__file__).resolve().parents[1]
os.chdir(root)
run_file = Path(os.environ.get('EDITOR_VERIFY_RUN_FILE', str(root/'evidence/source-spans-run.json')))
run = json.loads(run_file.read_text())
generation = str(uuid.UUID(run['generation_id']))
job_id = str(uuid.UUID(run['job_id']))
base = os.environ.get('EDITOR_VERIFY_BASE_URL', 'http://127.0.0.1:8810').rstrip('/')
headers = {'Authorization': 'Bearer '+(root/'secrets/api_token').read_text().strip()}


def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path, headers=headers), timeout=60) as response:
        return json.load(response)


def sql(query):
    return json.loads(subprocess.check_output(['docker', 'compose', 'exec', '-T',
        'postgres', 'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query], text=True))


record_cache = {}


def records(kind, page=None):
    # Completed generations are immutable. Compare each entire record kind once,
    # then validate pages in memory instead of spawning PostgreSQL 144 times.
    if snapshot_job['status'] == 'COMPLETED':
        if kind in record_cache:
            return [r for r in record_cache[kind] if page is None or r['data']['pdf_page'] == page]
        if page is not None:
            return [r for r in records(kind) if r['data']['pdf_page'] == page]
    items = []
    while True:
        batch = get(f'/v1/generations/{generation}/{kind}?offset={len(items)}&limit=100'
                    +(f'&pdf_page={page}' if page is not None else ''))
        items.extend(batch['items'])
        if not batch['has_more']:
            break
        assert batch['items'], 'EMPTY_PAGINATION'
    condition = f" AND data->>'pdf_page'='{int(page)}'" if page is not None else ''
    reference = sql("SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) "
                    f"ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='{generation}' "
                    f"AND kind='{kind}'"+condition)
    assert items == reference, f'API_PG_MISMATCH:{kind}:{page}'
    if snapshot_job['status'] == 'COMPLETED':
        record_cache[kind] = items
    return items


def tokens(value):
    # Preserve boundaries; no fuzzy matching, joining words or expected answers.
    value = unicodedata.normalize('NFKC', value).replace('İ', 'i').replace('I', 'ı').lower()
    return re.findall(r'[^\W_]+', value)


def contains(haystack, needle):
    return bool(needle) and any(haystack[i:i+len(needle)] == needle
                               for i in range(len(haystack)-len(needle)+1))


def grounded(refs, spans, page):
    assert refs and len(refs) == len(set(refs)), 'MISSING_OR_DUPLICATE_REFS'
    selected = [spans[ref]['data'] for ref in refs]
    assert all(s['status'] == 'TEXT_AGREED' and s['role'] == 'TEXT'
               and s['pdf_page'] == page for s in selected), 'UNVERIFIED_OR_CROSS_PAGE_SOURCE'
    assert len({s['render_sha256'] for s in selected}) == 1, 'MIXED_SOURCE_RENDER'
    return selected


def literal_attribution(item, spans, page):
    refs = item['source_span_refs']
    selected = grounded(refs, spans, page)
    text = '\n'.join(s['text'] for s in selected)
    origins = []
    for ref, row in zip(refs, selected):
        if origins:
            origins.append(None)
        origins.extend([ref]*len(row['text']))
    literal = item['source_text']
    assert literal and text.count(literal) == 1, 'LITERAL_ATTRIBUTION_NOT_UNIQUE_IN_SOURCE'
    start = text.index(literal)
    actual_refs = list(dict.fromkeys(r for r in origins[start:start+len(literal)] if r))
    assert actual_refs == refs, 'ATTRIBUTION_EXTRANEOUS_REFS'
    quote = item['quote']
    assert quote and literal.count(quote) == 1, 'QUOTE_NOT_UNIQUE_IN_ATTRIBUTION'
    quote_start = start+literal.index(quote)
    quote_end = quote_start+len(quote)
    actual_quote_refs = list(dict.fromkeys(r for r in origins[quote_start:quote_end] if r))
    assert actual_quote_refs == item['quote_span_refs'], 'QUOTE_REF_OFFSETS_DIFFER'
    grounded(item['quote_span_refs'], spans, page)
    assert quote_start > start and quote_end < start+len(literal), 'QUOTE_DELIMITERS_MISSING'
    assert (text[quote_start-1], text[quote_end]) in {
        ('"', '"'), ('“', '”'), ('"', '”'), ('“', '"'),
        ("'", "'"), ('‘', '’'), ("'", '’'), ('‘', "'")}, 'QUOTE_DELIMITERS_INVALID'
    suffix = literal[literal.index(quote)+len(quote)+1:].strip()
    assert item['label'] and suffix.endswith(item['label']), 'LABEL_NOT_LITERAL_SOURCE_SUFFIX'
    verb_part = suffix[:-len(item['label'])].strip()
    if verb_part.startswith('diye '):
        verb_part = verb_part[5:].strip()
    assert verb_part == item['reporting_verb'], 'VERB_OR_SUBJECT_SOURCE_DIFFERS'
    assert item['label_key'] == unicodedata.normalize('NFKC', item['label']).replace('İ', 'i').replace('I', 'ı').lower()
    assert item['status'] == 'EXPLICIT_TEXT_ATTRIBUTION'
    assert item['visual_identity_verified'] is False and item['eligible_for_synthesis'] is False


snapshot_job = get('/v1/jobs/'+job_id)
checks = records('page_checks')
completed = sorted({r['data']['pdf_page'] for r in checks})
assert completed, 'NO_COMPLETED_PAGES_TO_VERIFY'
counts = Counter()
pages = []
for page in completed:
    spans = {r['id']: r for r in records('source_spans', page)}
    character = records('character_evidence', page)
    claims_rows = records('page_claims', page)
    assert len(character) == len(claims_rows) == 1, 'MISSING_OR_DUPLICATE_PAGE_EVIDENCE'
    evidence = character[0]['data']; claims = claims_rows[0]['data']
    assert evidence['pipeline_version'] in ('source-spans-v5','source-spans-v6'), 'WRONG_PIPELINE_VERSION'
    assert evidence['page_role'] == claims['page_role']
    assert evidence['visual_identity_verified'] is False and evidence['eligible_for_synthesis'] is False
    attributions = evidence['attributions']
    if evidence['page_role'] != 'NARRATIVE':
        assert not attributions and not evidence['named_mentions'], 'NON_NARRATIVE_ATTRIBUTION'
    expected_mentions = {}
    for item in attributions:
        literal_attribution(item, spans, page)
        expected_mentions.setdefault(item['label_key'], set()).update(item['source_span_refs'])
    assert len(evidence['named_mentions']) == len(expected_mentions)
    for mention in evidence['named_mentions']:
        assert set(mention['source_span_refs']) == expected_mentions[mention['label_key']]
        assert any(item['label'] == mention['label'] and item['label_key'] == mention['label_key'] for item in attributions)
    speaker_count = 0
    for claim in claims['claims']+claims['blocked_claims']:
        assert claim['eligible_for_synthesis'] is False and claim['visual_identity_verified'] is False
        if claim['speaker'] is None:
            assert claim['speaker_status'] == 'UNKNOWN' and not claim['speaker_source_span_refs']
            continue
        assert claim['kind'] == 'STATEMENT' and claim['source_gate'] == 'MATCH'
        assert claim['speaker_status'] == 'EXPLICIT_TEXT_ATTRIBUTION'
        grounded(claim['span_refs'], spans, page)
        candidates = [a for a in attributions if set(claim['span_refs']) <= set(a['quote_span_refs'])
                      and contains(tokens(a['quote']), tokens(claim['quote']))]
        assert len(candidates) == 1, 'SPEAKER_ATTRIBUTION_AMBIGUOUS_OR_OUTSIDE_QUOTE'
        selected = candidates[0]
        assert claim['speaker'] == selected['label']
        assert claim['speaker_source_span_refs'] == selected['source_span_refs']
        assert claim['speaker_method'] == evidence['method']
        speaker_count += 1
    counts['attributions'] += len(attributions); counts['speaker_claims'] += speaker_count
    counts['named_mentions'] += len(evidence['named_mentions'])
    pages.append({'pdf_page': page, 'page_role': evidence['page_role'],
                  'attributions': len(attributions), 'speaker_claims': speaker_count, 'api_pg_equal': True})
job = get('/v1/jobs/'+job_id)
if snapshot_job['status'] == 'COMPLETED':
    assert completed == list(range(1, job['source_coverage']['expected_pages']+1)), 'INCOMPLETE_PAGE_COVERAGE'
assert all(r['data']['semantic_acceptance'] is False for r in checks)
report = {'generation_id': generation, 'job_id': job_id, 'job_status': job['status'], 'api': base,
          'snapshot_job_status': snapshot_job['status'],
          'full_page_coverage_verified': completed == list(range(1, job['source_coverage']['expected_pages']+1)),
          'checked_at': datetime.now(timezone.utc).isoformat(), 'completed_pages_checked': len(completed),
          'counts': dict(counts), 'pages': pages, 'actual_attribution_cases_present': counts['attributions'] > 0,
          'actual_speaker_cases_present': counts['speaker_claims'] > 0, 'semantic_acceptance': False,
          'visual_identity_acceptance': False, 'source_or_review_writes': 0,
          'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'status': 'PASS'}
destination = root/'evidence'/('character-evidence-verification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({**report, 'evidence': str(destination)}, ensure_ascii=False, indent=2))
