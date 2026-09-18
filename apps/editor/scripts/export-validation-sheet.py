#!/usr/bin/env python3
"""Export real accepted claims and their recorded source text as a labelling sheet.

The sheet is evaluation data.  It is written outside the application root, is
never read by production code, and carries no gate outcome so the labeller is
not biased.  Labels are filled by a person; nothing here decides anything.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

LABELS = 'SADIK | SADIK_DEGIL | KARARSIZ'
ERROR_CLASSES = ('OZNE_KAYMASI | KONUSMACI_YANLIS | KONUM_SAHIPLIK_EKLEME | ZAMAN_KAYMASI | '
                 'KESINLIK_KAYMASI | LISTE_GENELLEME | KAYNAKTA_OLMAYAN_AD | DIGER')

p = argparse.ArgumentParser()
p.add_argument('output', type=Path)
p.add_argument('eligible_claims', type=Path, nargs='+')
a = p.parse_args()
assert sys.platform.startswith('linux'), 'SERVER_ONLY'
assert 'editor-validation' in a.output.resolve().parts, 'VALIDATION_DATA_STAYS_OUTSIDE_APPLICATION_ROOT'

rows, seen = [], set()
for path in a.eligible_claims:
    proof = json.loads(path.read_bytes())
    for item in proof['items'] if isinstance(proof, dict) else proof:
        segments = item.get('review', {}).get('citation_review', {}).get('source_reading_segments')
        source = ' '.join(s['reading_text'] for s in segments) if segments else item['claim']['quote']
        claim = item['claim']['text']
        key = hashlib.sha256(json.dumps([source, claim], ensure_ascii=False).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        rows.append({'item_id': key[:16], 'kaynak_dosya': path.name, 'pdf_sayfa': item['page'],
                     'kaynak_metin': source.replace('\n', ' '), 'iddia': claim,
                     'etiket': '', 'hata_sinifi': '', 'not': ''})
a.output.parent.mkdir(parents=True, exist_ok=True)
with a.output.open('x', encoding='utf-8-sig', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
a.output.chmod(0o600)
print(json.dumps({'output': str(a.output), 'rows': len(rows), 'labels': LABELS, 'error_classes': ERROR_CLASSES},
                 ensure_ascii=False))
