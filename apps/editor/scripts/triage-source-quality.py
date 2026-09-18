#!/usr/bin/env python3
"""Measure real source blockers through API plus independent PostgreSQL reads.

No source text, review, claim or acceptance decision is changed.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid

root = Path(__file__).resolve().parents[1]
os.chdir(root)
run_file = root/os.environ.get('EDITOR_VERIFY_RUN_FILE', 'evidence/source-spans-run.json')
run = json.loads(run_file.read_text())
generation = str(uuid.UUID(run['generation_id']))
base = os.environ.get('EDITOR_VERIFY_BASE_URL', 'http://127.0.0.1:8810')
headers = {'Authorization': 'Bearer '+(root/'secrets/api_token').read_text().strip()}


def records(kind):
    result = []
    while True:
        url = f'{base}/v1/generations/{generation}/{kind}?offset={len(result)}&limit=100'
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
            batch = json.load(response)
        result.extend(batch['items'])
        if not batch['has_more']:
            break
        if not batch['items']:
            raise RuntimeError('EMPTY_PAGINATION_WITH_HAS_MORE')
    query = f"SELECT COALESCE(json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key),'[]'::json) FROM editor.records WHERE generation_id='{generation}' AND kind='{kind}'"
    reference = json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres',
        'psql','-U','postgres','-d','editor','-Atc',query], text=True))
    assert sorted(result, key=lambda row: row['record_key']) == reference, 'API_DB_MISMATCH:'+kind
    return result


spans = records('source_spans')
readings = records('page_readings')
claims = records('page_claims')
pending = [row for row in spans if row['data']['status'] != 'TEXT_AGREED']
issues = Counter(issue for row in pending for issue in row['data']['issues'])
combinations = Counter('|'.join(sorted(row['data']['issues'])) for row in pending)
pages = []
for reading in readings:
    page = reading['data']['pdf_page']
    page_spans = [row for row in spans if row['data']['pdf_page'] == page]
    page_pending = [row for row in pending if row['data']['pdf_page'] == page]
    assert len(page_spans) == reading['data']['span_count']
    assert len(page_pending) == reading['data']['review_spans']
    pages.append({'pdf_page': page, 'total': len(page_spans), 'review': len(page_pending),
        'issues': dict(Counter(issue for row in page_pending for issue in row['data']['issues'])),
        'source_span_ids': [row['id'] for row in page_pending]})
all_claims = [claim for row in claims for key in ('claims','blocked_claims') for claim in row['data'][key]]
report = {'at': datetime.now(timezone.utc).isoformat(), 'generation_id': generation,
    'run_file': str(run_file),
    'api': base, 'independent_pg_equal': True, 'total_spans': len(spans),
    'agreed': len(spans)-len(pending), 'review': len(pending), 'issue_counts': dict(issues),
    'issue_combinations': dict(combinations),
    'reread_states': dict(Counter(row['data'].get('reread_state','NOT_AVAILABLE') for row in pending)),
    'page_label_candidates': sum(row['data'].get('role') == 'PAGE_LABEL_CANDIDATE' for row in pending),
    'claim_gates': dict(Counter(claim['source_gate'] for claim in all_claims)),
    'synthesis_eligible_claims': sum(bool(claim['eligible_for_synthesis']) for claim in all_claims),
    'pages': sorted(pages, key=lambda page: (-page['review'], page['pdf_page'])),
    'semantic_acceptance': False, 'source_or_review_writes': 0}
destination = root/'evidence'/('source-quality-triage-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps({**{key: value for key,value in report.items() if key != 'pages'},
    'most_blocked_pages': [{key:value for key,value in page.items() if key != 'source_span_ids'} for page in report['pages'][:10]],
    'evidence': str(destination)}, ensure_ascii=False, indent=2))
