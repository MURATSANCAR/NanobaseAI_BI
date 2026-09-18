#!/usr/bin/env python3
"""Read-only, per-page API/PG coverage checks while a real analysis continues.

This is an interim source-accounting check, not semantic or full-book acceptance.
Generation and page IDs are explicit inputs; no book-specific expected answers.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
import uuid

assert sys.platform.startswith('linux') and os.environ.get('EDITOR_VERIFY_REMOTE_HOST') == socket.gethostname()
root = Path(os.environ['EDITOR_VERIFY_ROOT']).resolve()
base = os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/')
assert base.startswith('http://127.0.0.1:')
generation = str(uuid.UUID(sys.argv[1]))
pages = [int(value) for value in sys.argv[2:]]
assert pages and len(set(pages)) == len(pages) and all(page > 0 for page in pages)
headers = {'Authorization': 'Bearer ' + (root/'secrets/api_token').read_text().strip()}
report = {'generation_id': generation, 'pages': [], 'source_or_review_writes': 0,
          'model_calls': 0, 'semantic_acceptance': False, 'complete_book': False,
          'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
destination = root/'evidence'/('source-unit-pages-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def records(kind, page):
    rows = []
    while True:
        route = f'/v1/generations/{generation}/{kind}?pdf_page={page}&limit=100&offset={len(rows)}'
        with urllib.request.urlopen(urllib.request.Request(base+route, headers=headers), timeout=60) as response:
            batch = json.load(response)
        rows.extend(batch['items'])
        if not batch['has_more']:
            break
        assert batch['items'], 'PAGINATION_STALLED'
    query = ("SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) "
             f"FROM editor.records WHERE generation_id='{generation}' AND kind='{kind}' AND (data->>'pdf_page')::int={page}")
    reference = json.loads(subprocess.check_output(['docker', 'compose', 'exec', '-T', 'postgres', 'psql',
        '-U', 'postgres', '-d', 'editor', '-Atc', query], cwd=root, text=True))
    assert sorted(rows, key=lambda row: row['record_key']) == reference, 'API_PG_MISMATCH:'+kind
    return rows


try:
    for page in pages:
        claims = records('page_claims', page)
        assert len(claims) == 1, 'PAGE_CLAIMS_NOT_COMPLETED'
        data = claims[0]['data']
        spans = {row['id']: row['data'] for row in records('source_spans', page)}
        assert data['source_unit_method'] in ('source-unit-claims-v3', 'source-unit-claims-v4')
        units = data['source_units']; lookup = {unit['unit_id']: unit for unit in units}
        ledger = data['source_unit_coverage']; dispositions = ledger['unit_dispositions']
        assert len(lookup) == len(units) == ledger['catalogue_units'] and set(lookup) == set(dispositions)
        assert ledger['catalogue_sha256'] == digest(units) and ledger['accounting_complete'] is True
        assert ledger['semantic_complete'] is False and ledger['human_accepted'] is False
        for unit in units:
            refs = unit['span_refs']
            assert refs and len(refs) == len(set(refs)) and all(ref in spans for ref in refs)
            assert all(spans[ref]['pdf_page'] == page and spans[ref]['status'] == 'TEXT_AGREED'
                       and spans[ref]['role'] == 'TEXT' and spans[ref]['render_sha256'] == unit['render_sha256'] for ref in refs)
            assert unit['quote'] == '\n'.join(spans[ref]['text'] for ref in refs)
            assert unit['sha256'] == digest({key: unit[key] for key in ('pdf_page', 'span_refs', 'quote', 'render_sha256')})
        for candidate in data['claims'] + data['blocked_claims']:
            unit = lookup[candidate['source_unit_id']]
            assert candidate['quote_origin'] == 'IMMUTABLE_OCR_UNIT_SELECTION'
            assert candidate['quote'] == unit['quote'] and candidate['span_refs'] == unit['span_refs']
            assert candidate['source_unit_sha256'] == unit['sha256']
            assert candidate['text'] == candidate['model_candidate']['text']
        agreed = {ref for ref, span in spans.items() if span['status'] == 'TEXT_AGREED' and span['role'] == 'TEXT'}
        included = {ref for unit in units for ref in unit['span_refs']}
        assert ledger['agreed_text_span_refs'] == sorted(agreed)
        assert ledger['catalogued_span_refs'] == sorted(included)
        assert ledger['uncatalogued_agreed_span_refs'] == sorted(agreed-included)
        assert all(value['status'] in ('CANDIDATE', 'NO_CLAIM', 'NEEDS_REVIEW', 'UNPROCESSED') for value in dispositions.values())
        report['pages'].append({'pdf_page': page, 'status': 'PASS', 'units': len(units),
            'candidate_count': len(data['claims'])+len(data['blocked_claims']),
            'uncatalogued_agreed_spans': len(agreed-included),
            'needs_review_units': sum(value['status'] == 'NEEDS_REVIEW' for value in dispositions.values()),
            'unprocessed_units': sum(value['status'] == 'UNPROCESSED' for value in dispositions.values()),
            'page_claims_sha256': digest(data)})
    report['status'] = 'PASS'
except Exception as error:
    report.update(status='FAILED', error_type=type(error).__name__, reason=str(error))
    raise
finally:
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'status': report['status'], 'pages_checked': len(report['pages']), 'evidence': str(destination)}))
