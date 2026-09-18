#!/usr/bin/env python3
"""Read-only profile of direct-speech marking and first-person predicates in page texts.

Input on stdin: {"book label": {"page number": "page text"}} taken from prepared
source artifacts.  Reports counts only; no book text is written to the evidence.
It answers whether the assumptions of the person-agreement candidate (quotation
marks delimit speech; first-person finite verbs sit inside speech) hold on a book.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import logging
from pathlib import Path
import re
import sys

p = argparse.ArgumentParser()
p.add_argument('module', type=Path)
p.add_argument('evidence_dir', type=Path)
a = p.parse_args()
assert sys.platform.startswith('linux'), 'SERVER_ONLY'
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


DASH_LINE = re.compile(r'^\s*[—–-]\s*\S', re.M)
raw = sys.stdin.buffer.read()
books, report = json.loads(raw), {}
for label, pages in books.items():
    c = Counter()
    for number, text in pages.items():
        if not text.strip():
            c['empty_pages'] += 1
            continue
        c['pages_with_text'] += 1
        page_words = gate.words(text)
        c['words'] += len(page_words)
        c['unanalysed_words'] += sum(not analyze(w['stem'] + (w['suffix'] or '')) for w in page_words)
        spans = gate.quoted(text)
        c['quoted_spans'] += len(spans)
        c['uncertain_quoted_spans'] += sum(not s[2] for s in spans)
        c['pages_without_any_quotation_mark'] += not spans
        c['dialogue_dash_lines'] += len(DASH_LINE.findall(text))
        usable, skipped = gate.first_person_predicates(text, analyze)
        c['first_person_predicates'] += len(usable) + len(skipped)
        c['gate_applicable'] += len(usable)
        for item in skipped:
            c['gate_not_applicable:' + item['reason']] += 1
    report[label] = dict(sorted(c.items()))
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out = a.evidence_dir / f'utterance-profile-probe-{stamp}.json'
out.write_text(json.dumps({'input_sha256': hashlib.sha256(raw).hexdigest(),
                           'module_sha256': hashlib.sha256(a.module.read_bytes()).hexdigest(),
                           'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                           'analyzer': 'zeyrek', 'model_calls': 0, 'application_writes': 0,
                           'book_text_stored': False, 'books': report}, ensure_ascii=False, indent=1))
print(json.dumps({'evidence': str(out), 'books': report}, ensure_ascii=False, indent=1))
