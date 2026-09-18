#!/usr/bin/env python3
"""Read-only person-agreement replay over a recorded eligible-claims proof.

Runs on the deployment server inside the isolated morphology environment.
No model call, no application or database write.  The proof file supplies real
claims and their recorded source reading text; expected answers are not read.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import sys

p = argparse.ArgumentParser()
p.add_argument('eligible_claims', type=Path)
p.add_argument('module', type=Path)
p.add_argument('evidence_dir', type=Path)
a = p.parse_args()
assert sys.platform.startswith('linux'), 'SERVER_ONLY'

logging.disable(logging.CRITICAL)
import zeyrek  # noqa: E402

spec = importlib.util.spec_from_file_location('source_person_agreement', a.module)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

analyzer = zeyrek.MorphAnalyzer()
cache = {}


def analyze(word):
    if word not in cache:
        cache[word] = [(r.dict_item.lemma, r.pos.value, [m[0].id_ for m in r.morphemes]) for r in analyzer._parse(word)]
    return cache[word]


proof_bytes = a.eligible_claims.read_bytes()
proof = json.loads(proof_bytes)
items = proof['items'] if isinstance(proof, dict) else proof
assert items and (isinstance(proof, list) or proof['application_writes'] == 0)

results = []
for item in items:
    segments = item.get('review', {}).get('citation_review', {}).get('source_reading_segments')
    source = ' '.join(s['reading_text'] for s in segments) if segments else item['claim']['quote']
    claim = item['claim']['text']
    outcome = gate.review(source, claim, analyze)
    results.append({
        'pdf_page': item['page'], 'claim_id': item['claim_id'],
        'source': source, 'claim': claim,
        'person': outcome, 'tense_shifts': gate.tense_shifts(source, claim, analyze),
    })

unknown = sorted(w for w, r in cache.items() if not r)
summary = {
    'claims': len(results),
    'source_with_first_person_predicate': sum(bool(r['person']['source_first_person_predicates']) for r in results),
    'claims_reusing_such_predicate': sum(bool(r['person']['transfers']) for r in results),
    'needs_review': sum(r['person']['status'] == 'NEEDS_REVIEW' for r in results),
    'not_applicable': sum(r['person']['status'] == 'NOT_APPLICABLE' for r in results),
    'tense_shift_claims': sum(bool(r['tense_shifts']) for r in results),
    'distinct_words': len(cache), 'unanalysed_words': len(unknown),
}
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out = a.evidence_dir / f'person-agreement-probe-{stamp}.json'
out.write_text(json.dumps({
    'generation_id': proof['generation_id'] if isinstance(proof, dict) else None, 'input': a.eligible_claims.name,
    'input_sha256': hashlib.sha256(proof_bytes).hexdigest(),
    'module_sha256': hashlib.sha256(a.module.read_bytes()).hexdigest(),
    'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'gate_version': gate.VERSION, 'analyzer': f'zeyrek=={zeyrek.__version__}' if hasattr(zeyrek, '__version__') else 'zeyrek',
    'model_calls': 0, 'application_writes': 0, 'semantic_acceptance': False,
    'summary': summary, 'unanalysed_words': unknown, 'results': results,
}, ensure_ascii=False, indent=1))
print(json.dumps({'evidence': str(out), **summary}, ensure_ascii=False))
for r in results:
    if r['person']['status'] == 'NEEDS_REVIEW' or r['tense_shifts']:
        print(f"\n[pdf {r['pdf_page']}] {r['person']['reason']}")
        print('  kaynak:', r['source'][:300])
        print('  iddia :', r['claim'])
        for c in r['person']['conflicts']:
            print('  çakışma:', c['source_predicate'], c['persons'], '->', c['claim_name'], c['claim_case'])
        for s in r['tense_shifts']:
            print('  zaman:', s['lemma'], s['source_forms'], '->', s['claim_word'], s['claim_tenses'])
