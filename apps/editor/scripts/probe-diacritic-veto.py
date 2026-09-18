#!/usr/bin/env python3
"""Read-only replay of the diacritic-veto candidate over a recorded OCR residual audit.

Independent readers are the regional PaddleOCR text, the full-page Tesseract text
and the usable PDF text layer.  Tesseract crop rereads share an engine with the
full-page Tesseract reading, so they are reported but never counted as support.
No model call, no application or database write, no text correction.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import sys

p = argparse.ArgumentParser()
p.add_argument('residual_audit', type=Path)
p.add_argument('module', type=Path)
p.add_argument('evidence_dir', type=Path)
a = p.parse_args()
assert sys.platform.startswith('linux'), 'SERVER_ONLY'
logging.disable(logging.CRITICAL)
import zeyrek  # noqa: E402

spec = importlib.util.spec_from_file_location('source_diacritic_witness', a.module)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
analyzer, cache = zeyrek.MorphAnalyzer(), {}


def is_word(word):
    if word not in cache:
        cache[word] = bool(analyzer._parse(word))
    return cache[word]


audit_bytes = a.residual_audit.read_bytes()
audit = json.loads(audit_bytes)
assert audit['writes_to_source_or_review'] == 0 and audit['api_pg_equal'] is True
counts, released = Counter(), []
for region in audit['regions']:
    readings = {'paddle_region': region.get('region_text') or '', 'tesseract_full_page': region.get('secondary_text') or ''}
    if region.get('pdf_usable'):
        readings['pdf_text_layer'] = region.get('pdf_text') or ''
    outcome = gate.review(readings, is_word)
    counts['regions'] += 1
    counts['reason:' + outcome['reason']] += 1
    if outcome['decision'] != 'OBJECTION_VOID':
        continue
    agreed = gate.tokens(readings[outcome['supporters'][0]])
    rereads = [gate.tokens(r.get('text') or '') for r in (region.get('reread_measurement') or {}).get('readings', [])]
    side = ('agreed' if any(r == agreed for r in rereads) else
            'objector' if any(r == gate.tokens(readings[outcome['objectors'][0]]) for r in rereads) else 'neither')
    counts['released'] += 1
    counts['released:role:' + region['role']] += 1
    counts['released:objector:' + outcome['objectors'][0]] += 1
    counts['released:same_engine_reread_sides_with:' + side] += 1
    released.append({'id': region['id'], 'pdf_page': region['pdf_page'], 'class': region['class'],
                     'readings': readings, 'outcome': outcome, 'same_engine_reread_sides_with': side})
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out = a.evidence_dir / f'diacritic-veto-probe-{stamp}.json'
out.write_text(json.dumps({
    'generation_id': audit['generation_id'], 'input': a.residual_audit.name,
    'input_sha256': hashlib.sha256(audit_bytes).hexdigest(),
    'module_sha256': hashlib.sha256(a.module.read_bytes()).hexdigest(),
    'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'gate_version': gate.VERSION, 'analyzer': 'zeyrek', 'model_calls': 0, 'application_writes': 0,
    'text_corrections': 0, 'semantic_acceptance': False,
    'counts': dict(sorted(counts.items())), 'released': released}, ensure_ascii=False, indent=1))
print(json.dumps({'evidence': str(out), **dict(sorted(counts.items()))}, ensure_ascii=False, indent=1))
for r in released:
    print(r['pdf_page'], r['outcome']['objectors'], [(w['agreed'], w['objected']) for w in r['outcome']['words']])
