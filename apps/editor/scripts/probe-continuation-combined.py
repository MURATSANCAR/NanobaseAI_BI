#!/usr/bin/env python3
"""Offline re-score of the continuation probe: deterministic reporting-clause rule
first, recorded model probabilities only where the rule does not apply.

No model call.  Inputs: page texts on stdin (same export as the model probe), the
recorded model evidence file, and the person-agreement module (for the verb check).
Labels come from quotation marks in marked books.  A wrapped line that opens a new
quotation is excluded: without the marks, same speaker or new speaker is undecidable.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import re
import sys

p = argparse.ArgumentParser()
p.add_argument('model_evidence', type=Path)
p.add_argument('module', type=Path)
p.add_argument('evidence_dir', type=Path)
a = p.parse_args()
logging.disable(logging.CRITICAL)
import zeyrek  # noqa: E402

spec = importlib.util.spec_from_file_location('source_person_agreement', a.module)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
analyzer, cache = zeyrek.MorphAnalyzer(), {}


def analyze(word):
    if word not in cache:
        cache[word] = [(r.dict_item.lemma, r.pos.value, [m[0].id_ for m in r.morphemes]) for r in analyzer._parse(word)]
    return cache[word]


OPENING, CLOSING = '“„«‘"', '”»"'
MARKS = re.compile('[' + re.escape(OPENING + CLOSING) + ']')


def quote_spans(text):
    spans, start = [], None
    for i, ch in enumerate(text):
        if ch == '"':
            prev = text[i - 1:i]
            opening = not prev.strip() or not (prev.isalnum() or prev in '.!?…,')
        elif ch in OPENING:
            opening = True
        elif ch in CLOSING:
            opening = False
        else:
            continue
        if opening and start is None:
            start = i + 1
        elif not opening and start is not None:
            spans.append((start, i)); start = None
    if start is not None:
        spans.append((start, len(text)))
    return spans


def examples(text):
    lines, offset, starts, out = text.split('\n'), 0, [], []
    for line in lines:
        starts.append(offset); offset += len(line) + 1
    spans = quote_spans(text)
    for i in range(len(lines) - 1):
        first, second = lines[i], lines[i + 1]
        if not first.strip() or not second.strip() or first.lstrip()[:1] not in OPENING:
            continue
        head = starts[i + 1] + len(second) - len(second.lstrip())
        # A wrapped line that opens a new quotation is either the same speaker again or
        # a new speaker; with the marks removed that is undecidable, so it is excluded.
        if second.lstrip()[:1] in OPENING:
            out.append({'excluded': True})
            continue
        inside = any(s <= head < e for s, e in spans)
        out.append({'first': '- ' + MARKS.sub('', first).strip(), 'second': MARKS.sub('', second).strip(),
                    'label': 'A' if inside else 'B'})
    return out


def rule(first, second):
    """Reporting clause on the dash line that runs onto the next line: 'B' (the next
    line continues narration).  Anything else is left to the model: None."""
    text = first[2:] if first.startswith('- ') else first
    for word in gate.words(text):
        before = text[:word['start']].rstrip()
        if before[-1:] not in tuple(',!?…') and not before.endswith('...'):
            continue
        words = [w for w in gate.words(text) if w['start'] >= word['start']]
        verb = words[1] if word['stem'] == gate.QUOTATIVE and word['suffix'] is None and len(words) > 1 else words[0]
        parsed = gate.readings(verb, analyze)
        # Reporting verbs often have a nominal homograph ("güldü": gül, "atıldı": atıl), so
        # one finite third-person verb-root reading suffices after speech punctuation.
        if verb['surface'][0].isupper() or not any(
                r['verbal_root'] and r['person'] in ('A3sg', 'A3pl') and gate.REPORT_TENSES & set(r['tenses']) for r in parsed):
            continue
        tail = text[verb['end']:]
        # A clause closed on this line says nothing about the next line: it may be
        # resumed speech or a new narrator paragraph; only line geometry could tell.
        return None if re.search(r'[.:;]', tail) else 'B'
    return None


model = json.loads(a.model_evidence.read_bytes())
probs = {(r['first'], r['second']): r['p'] for b in model['books'].values() for r in b['rows']}
books = json.loads(sys.stdin.buffer.read())
report = {}
for label, pages in books.items():
    c, wrong = Counter(), []
    for text in pages.values():
        for ex in examples(text):
            if ex.get('excluded'):
                c['excluded_new_quotation'] += 1
                continue
            c['examples'] += 1
            decided_by_rule = rule(ex['first'], ex['second'])
            pm = probs.get((ex['first'], ex['second']))
            model_choice = max(pm, key=pm.get) if pm else None
            confident = pm is not None and max(pm.values()) >= 0.8 and model_choice != 'C'
            c['model_confident'] += confident
            c['model_confident_correct'] += confident and model_choice == ex['label']
            if decided_by_rule:
                c['rule_decided'] += 1
                c['rule_correct'] += decided_by_rule == ex['label']
                final = decided_by_rule
            elif confident:
                final = model_choice
            else:
                c['combined_abstained'] += 1
                continue
            c['combined_decided'] += 1
            c['combined_correct'] += final == ex['label']
            if final != ex['label']:
                wrong.append([ex['first'][:70], ex['second'][:50], ex['label'], final, 'rule' if decided_by_rule else 'model'])
    report[label] = {'counts': dict(sorted(c.items())), 'combined_wrong': wrong}
out = a.evidence_dir / ('continuation-combined-' + a.model_evidence.stem.split('-')[-1] + '.json')
out.write_text(json.dumps({'model_evidence': a.model_evidence.name,
                           'module_sha256': hashlib.sha256(a.module.read_bytes()).hexdigest(),
                           'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           'model_calls': 0, 'application_writes': 0, 'book_text_stored': False,
                           'books': {k: {'counts': v['counts']} for k, v in report.items()}}, ensure_ascii=False, indent=1))
print(out)
for k, v in report.items():
    print(k, json.dumps(v['counts'], ensure_ascii=False))
    for w in v['combined_wrong']:
        print('   YANLIŞ', w)
