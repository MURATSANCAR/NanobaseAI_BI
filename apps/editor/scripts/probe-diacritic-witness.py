#!/usr/bin/env python3
"""Read-only measurement over a recorded OCR residual audit.

Two questions, no model call, no application or database write:
1. How many reader disagreements are Unicode encoding differences only
   (canonical equivalence, NFC)?
2. Where two readers differ only in Turkish diacritics, how often does a
   morphological analyzer accept exactly one of the two produced words?

The analyzer never produces text.  A witness can only choose between strings
that the readers themselves produced; nothing is corrected here.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
import unicodedata

p = argparse.ArgumentParser()
p.add_argument('residual_audit', type=Path)
p.add_argument('evidence_dir', type=Path)
a = p.parse_args()
assert sys.platform.startswith('linux'), 'SERVER_ONLY'

logging.disable(logging.CRITICAL)
import zeyrek  # noqa: E402

analyzer = zeyrek.MorphAnalyzer()
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
FOLD = str.maketrans('ıİşŞğĞçÇöÖüÜâÂîÎûÛ', 'iIsSgGcCoOuUaAiIuU')
TURKISH = set('abcçdefgğhıijklmnoöprsştuüvyzâîûqwx')
valid_cache = {}


def lower(text):
    return text.replace('İ', 'i').replace('I', 'ı').lower()


def tokens(text, normalise):
    text = unicodedata.normalize('NFC', text) if normalise else text
    return [lower(w) for w in WORD.findall(text)]


def fold(word):
    return unicodedata.normalize('NFKD', word.translate(FOLD)).encode('ascii', 'ignore').decode().lower()


def valid(word):
    if word not in valid_cache:
        valid_cache[word] = bool(analyzer._parse(word))
    return valid_cache[word]


audit_bytes = a.residual_audit.read_bytes()
audit = json.loads(audit_bytes)
assert audit['writes_to_source_or_review'] == 0 and audit['api_pg_equal'] is True

counts, regions = Counter(), []
for region in audit['regions']:
    readers = {'paddle_region': region.get('region_text') or '', 'tesseract': region.get('secondary_text') or ''}
    if region.get('pdf_usable'):
        readers['pdf'] = region.get('pdf_text') or ''
    for reading in (region.get('reread_measurement') or {}).get('readings', []):
        readers[f"tesseract_psm{reading['psm']}"] = reading.get('text') or ''
    counts['regions'] += 1
    if any(unicodedata.normalize('NFC', t) != t for t in readers.values()):
        counts['regions_with_non_nfc_reader_text'] += 1
    for name, text in readers.items():
        foreign = sorted({c for c in lower(unicodedata.normalize('NFC', text)) if c.isalpha() and c not in TURKISH})
        if foreign:
            counts[f'{name}:regions_with_non_turkish_letter'] += 1
            for c in foreign:
                counts[f'{name}:letter:U+{ord(c):04X}:{c}'] += 1
    primary = 'paddle_region'
    pdf_tokens = tokens(readers['pdf'], True) if 'pdf' in readers else None
    record = {'id': region['id'], 'pdf_page': region['pdf_page'], 'class': region['class'], 'pairs': []}
    for other in [k for k in readers if k != primary]:
        raw_a, raw_b = tokens(readers[primary], False), tokens(readers[other], False)
        nfc_a, nfc_b = tokens(readers[primary], True), tokens(readers[other], True)
        if not nfc_a or not nfc_b:
            continue
        if raw_a != raw_b and nfc_a == nfc_b:
            counts[f'{other}:equal_after_nfc_only'] += 1
        if nfc_a == nfc_b or len(nfc_a) != len(nfc_b) or [fold(w) for w in nfc_a] != [fold(w) for w in nfc_b]:
            continue
        counts[f'{other}:diacritics_only_region'] += 1
        decided, words = True, []
        for index, (left, right) in enumerate(zip(nfc_a, nfc_b)):
            if left == right:
                continue
            ok_left, ok_right = valid(left), valid(right)
            verdict = ('ONLY_' + primary.upper() if ok_left and not ok_right else
                       'ONLY_' + other.upper() if ok_right and not ok_left else
                       'BOTH_VALID' if ok_left else 'NEITHER_VALID')
            counts[f'{other}:word:{verdict}'] += 1
            decided &= verdict.startswith('ONLY_')
            if verdict.startswith('ONLY_') and other == 'tesseract':
                chosen = left if verdict == 'ONLY_' + primary.upper() else right
                reference = pdf_tokens[index] if pdf_tokens and len(pdf_tokens) == len(nfc_a) else None
                outcome = 'no_aligned_pdf' if reference is None else 'agrees_with_pdf' if reference == chosen else 'differs_from_pdf'
                counts[f'witness_vs_pdf:{outcome}'] += 1
                counts[f'witness_vs_pdf:{outcome}:len{min(len(chosen), 4)}{"+" if len(chosen) >= 4 else ""}'] += 1
                if outcome == 'differs_from_pdf':
                    print('PDF FARKI', region['pdf_page'], {'seçilen': chosen, 'pdf': reference, 'paddle': left, 'tesseract': right})
            words.append({primary: left, other: right, 'verdict': verdict})
        counts[f'{other}:region_decidable' if decided else f'{other}:region_undecidable'] += 1
        record['pairs'].append({'other': other, 'decidable': decided, 'words': words})
    if record['pairs']:
        regions.append(record)

stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
out = a.evidence_dir / f'diacritic-witness-probe-{stamp}.json'
out.write_text(json.dumps({
    'generation_id': audit['generation_id'], 'input': a.residual_audit.name,
    'input_sha256': hashlib.sha256(audit_bytes).hexdigest(),
    'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'analyzer': 'zeyrek', 'model_calls': 0, 'application_writes': 0, 'text_corrections': 0,
    'semantic_acceptance': False, 'counts': dict(sorted(counts.items())), 'regions': regions,
}, ensure_ascii=False, indent=1))
print(json.dumps({'evidence': str(out), **dict(sorted(counts.items()))}, ensure_ascii=False, indent=1))
