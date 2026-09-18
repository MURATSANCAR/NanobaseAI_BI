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


record_cache={}
def records(kind, page):
    if (kind,page) in record_cache:return record_cache[kind,page]
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
    record_cache[kind,page]=rows
    return rows


try:
    for page in pages:
        claims = records('page_claims', page)
        assert len(claims) == 1, 'PAGE_CLAIMS_NOT_COMPLETED'
        data = claims[0]['data']
        if data.get('source_unit_method')=='source-unit-claims-v4':
            purpose=data['proposal_page_purpose'];context_rows=records('page_context_roles',page)
            assert len(context_rows)==1 and purpose['record_id']==context_rows[0]['id'],'PURPOSE_RECORD_SCOPE'
            context=context_rows[0]['data']
            assert purpose['record_sha256']==digest(context),'PURPOSE_RECORD_HASH'
            assert context['classification_stage']=='BEFORE_CLAIM_PROPOSAL' and context['input_claim_candidates'] is False
            neighbours=[]
            for neighbour in range(max(1,page-1),page+2):
                evidence=records('evidence',neighbour)
                if not evidence:continue
                assert len(evidence)==1
                layout_rows=records('layout_regions',neighbour);assert len(layout_rows)==1
                layout=layout_rows[0]['data'];regions=[]
                for source in records('source_spans',neighbour)+records('source_fragments',neighbour):
                    d=source['data']
                    assert d['evidence_refs']==[evidence[0]['id']] and d['render_sha256']==evidence[0]['data']['ocr_render_sha256']
                    agreed=d['status']=='TEXT_AGREED' and d['role']=='TEXT'
                    regions.append({'ref':source['id'] if agreed else None,'can_cite':agreed,
                        'text':d['text'] if agreed else '[UNVERIFIED_REGION]','bbox':d['bbox'],
                        'is_verified_subregion':bool(agreed and d.get('parent_source_span_id'))})
                neighbours.append({'pdf_page':neighbour,'regions':regions,
                    'balloon_count':len(layout.get('balloon_candidates',[])),
                    'picture_count':sum(r.get('type')=='PICTURE' for r in layout.get('regions',[]))})
            assert purpose['input_sha256']==context['input_sha256']==digest({'target_page':page,'pages':neighbours}),'PURPOSE_INPUT_HASH'
            characters=records('character_evidence',page);assert len(characters)==1
            assert characters[0]['data']['page_role']==data['page_role'],'CHARACTER_PAGE_ROLE_MISMATCH'
            if purpose['passed']:
                assert purpose['page_role']==data['page_role']==context['page_role']
                assert context['content_scope']==context['review']['content_scope']=='STORY_WORLD'
                assert context['eligible_for_identity_context'] and context['review']['supported']
                assert context['uncertainty_review_complete'] and context['blocking_uncertainties']==[]
            else:
                assert data['page_role']=='UNKNOWN' and not data['claims'] and not data['blocked_claims']
                assert data['source_unit_coverage']['proposal_blocked_by_page_purpose']
            ordering_query=("SELECT (a.created_at<=b.created_at)::text FROM editor.records a,editor.records b "
                f"WHERE a.id='{context_rows[0]['id']}' AND b.id='{claims[0]['id']}' AND a.generation_id=b.generation_id")
            ordering=subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',ordering_query],cwd=root,text=True).strip()
            assert ordering=='true','CLAIMS_CREATED_BEFORE_PURPOSE'
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
