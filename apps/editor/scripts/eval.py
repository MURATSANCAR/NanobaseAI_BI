#!/usr/bin/env python3
"""Evaluation store and regression runner: labels -> candidates -> metrics.

Labels and raw candidate outputs live in PostgreSQL schema ``editor_eval``, owned
by the migration owner.  The application role gets no privilege on it, so
production code cannot read labels or expected answers; that separation is
enforced by the database, not by convention.  Qdrant is not used here.

Run inside the installation with the owner secret, e.g.
  docker compose run --rm --no-deps -v "$PWD/scripts:/eval:ro" -v "$IN:/in:ro" \\
      --entrypoint python migrate /eval/eval.py <command> ...

Commands
  init                                   create the schema (idempotent)
  load   TASK EVIDENCE --set NAME        create items from a recorded evidence file
  export TASK --set NAME OUT.csv         labelling sheet; carries no candidate output
  import TASK CSV --annotator NAME       store labels (one row per item and annotator)
  run    TASK EVIDENCE --method M --version V   store raw candidate outputs
  report TASK --set NAME [--json OUT]    metrics per method, agreement, calibration

Tasks: speech_boundary, ocr_region, claim_faithfulness, narrator_identity.
Items are keyed by a hash of their input, so reloading is idempotent.  A fixed
split (input hash) separates calibration items from held-out test items;
thresholds are chosen on calibration only and reported on test.
"""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import unicodedata

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

TASKS = ('speech_boundary', 'ocr_region', 'claim_faithfulness', 'narrator_identity')
LABELS = {
    'speech_boundary': {'boundary': ('CONTINUES', 'ENDS', 'UNCERTAIN')},
    'claim_faithfulness': {'verdict': ('FAITHFUL', 'NOT_FAITHFUL', 'AMBIGUOUS'),
                           'error_class': ('', 'MISSING_SUBJECT', 'WRONG_SUBJECT', 'WRONG_PREDICATE',
                                           'ADDED_LOCATION_OR_POSSESSION', 'TENSE_SHIFT', 'CERTAINTY_SHIFT',
                                           'LIST_GENERALISATION', 'NAME_NOT_IN_SOURCE', 'OTHER')},
    'ocr_region': {'error_class': ('', 'NO_ERROR', 'DIACRITIC_ONLY', 'WRONG_BASE_LETTER', 'SEGMENTATION',
                                   'TEXT_LAYER_CONFLICT', 'FONT_ARTIFACT', 'UNREADABLE')},
    'narrator_identity': {},
}
FREE_TEXT = {'ocr_region': ('gold_text', 'proper_nouns'),
             'claim_faithfulness': ('subject_span', 'predicate_span', 'note'),
             'speech_boundary': ('note',),
             'narrator_identity': ('narrator', 'evidence', 'note')}
SCHEMA = '''
CREATE SCHEMA IF NOT EXISTS editor_eval;
REVOKE ALL ON SCHEMA editor_eval FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='editor_app') THEN
    EXECUTE 'REVOKE ALL ON SCHEMA editor_eval FROM editor_app';
  END IF;
END $$;
CREATE TABLE IF NOT EXISTS editor_eval.items (
  id text PRIMARY KEY, task text NOT NULL, label_set text NOT NULL,
  book text, pdf_page int, split text NOT NULL CHECK(split IN ('calibration','test')),
  input jsonb NOT NULL, source_evidence text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS items_task_set ON editor_eval.items(task, label_set);
CREATE TABLE IF NOT EXISTS editor_eval.labels (
  item_id text NOT NULL REFERENCES editor_eval.items(id), annotator text NOT NULL,
  label jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(item_id, annotator));
CREATE TABLE IF NOT EXISTS editor_eval.candidate_runs (
  id text PRIMARY KEY, task text NOT NULL, method text NOT NULL, version text NOT NULL,
  source_evidence text NOT NULL, source_sha256 text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS editor_eval.candidate_outputs (
  run_id text NOT NULL REFERENCES editor_eval.candidate_runs(id),
  item_id text NOT NULL REFERENCES editor_eval.items(id),
  decision text, score double precision, raw jsonb NOT NULL,
  PRIMARY KEY(run_id, item_id));
'''


def connect():
    secret = Path('/run/secrets/db_owner').read_text().strip()
    return psycopg.connect(host='postgres', dbname=os.environ.get('EDITOR_DB_NAME', 'editor'), user='editor_owner',
                           password=secret, connect_timeout=5, row_factory=dict_row)


def key(task, value):
    return hashlib.sha256(json.dumps([task, value], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def split_of(item_id):
    return 'test' if int(item_id[:8], 16) % 5 == 0 else 'calibration'


# ---- loaders: recorded evidence -> items (input only, never a gate outcome) ----

DASH_LINE = __import__('re').compile(r'^\s*[\u2014\u2013-]\s*(?=\S)')


def items_speech(evidence):
    """Either a recorded continuation probe ({'books': {b: {'rows': ...}}}) or raw page
    texts ({book: {page: text}}); from page texts every dialogue-dash line and the line
    under it becomes one boundary item, so dash books are labelled on their own form."""
    if 'books' in evidence and all(isinstance(v, dict) and 'rows' in v for v in evidence['books'].values()):
        for book, value in evidence['books'].items():
            for row in value['rows']:
                yield book, int(row['page']), {'first': row['first'], 'second': row['second']}
        return
    for book, pages in evidence.items():
        for page, text in pages.items():
            lines = [line for line in text.split('\n')]
            for i in range(len(lines) - 1):
                if DASH_LINE.match(lines[i]) and lines[i + 1].strip() and not DASH_LINE.match(lines[i + 1]):
                    yield book, int(page), {'first': lines[i].strip(), 'second': lines[i + 1].strip()}


def items_ocr(evidence):
    for r in evidence['regions']:
        readers = {'paddle_region': r.get('region_text') or '', 'tesseract_full_page': r.get('secondary_text') or ''}
        if r.get('pdf_usable'):
            readers['pdf_text_layer'] = r.get('pdf_text') or ''
        for reading in (r.get('reread_measurement') or {}).get('readings', []):
            readers[f"tesseract_psm{reading['psm']}"] = reading.get('text') or ''
        yield None, r['pdf_page'], {'span_id': r['id'], 'bbox': r['bbox'], 'readers': readers,
                                    'audit_class': r['class']}


def items_claims(evidence):
    for item in evidence['items'] if isinstance(evidence, dict) else evidence:
        segments = item.get('review', {}).get('citation_review', {}).get('source_reading_segments')
        source = '\n'.join(s['reading_text'] for s in segments) if segments else item['claim']['quote']
        yield None, item['page'], {'claim_id': item['claim_id'], 'claim': item['claim']['text'], 'source': source}


LOADERS = {'speech_boundary': items_speech, 'ocr_region': items_ocr, 'claim_faithfulness': items_claims}


def cmd_init(db, a):
    db.execute(SCHEMA)
    print('editor_eval hazır; editor_app yetkisi yok')


def cmd_load(db, a):
    raw = Path(a.evidence).read_bytes()
    evidence, count = json.loads(raw), 0
    for book, page, value in LOADERS[a.task](evidence):
        item_id = key(a.task, value)
        cur = db.execute('''INSERT INTO editor_eval.items(id,task,label_set,book,pdf_page,split,input,source_evidence)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING''',
                         (item_id, a.task, a.set, book or a.book, page, split_of(item_id), Jsonb(value), Path(a.evidence).name))
        count += cur.rowcount
    print(json.dumps({'task': a.task, 'set': a.set, 'new_items': count}))


def cmd_export(db, a):
    rows = db.execute('SELECT id,book,pdf_page,input FROM editor_eval.items WHERE task=%s AND label_set=%s ORDER BY book,pdf_page,id',
                      (a.task, a.set)).fetchall()
    fields = list(LABELS[a.task]) + list(FREE_TEXT[a.task])
    with open(a.out, 'x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['item_id', 'kitap', 'pdf_sayfa', 'girdi'] + fields)
        for r in rows:
            shown = r['input'] if a.task != 'ocr_region' else {'okuyucular': r['input']['readers']}
            writer.writerow([r['id'], r['book'] or '', r['pdf_page'], json.dumps(shown, ensure_ascii=False)] + [''] * len(fields))
    print(json.dumps({'out': a.out, 'rows': len(rows), 'allowed': {k: v for k, v in LABELS[a.task].items()}}, ensure_ascii=False))


def cmd_import(db, a):
    stored, skipped = 0, []
    with open(a.csv, encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            label = {k: (row.get(k) or '').strip() for k in list(LABELS[a.task]) + list(FREE_TEXT[a.task])}
            if not any(label.get(k) for k in LABELS[a.task]) and not label.get('gold_text') and not label.get('narrator'):
                continue
            bad = [k for k, allowed in LABELS[a.task].items() if label.get(k) and label[k] not in allowed]
            if bad or not db.execute('SELECT 1 FROM editor_eval.items WHERE id=%s AND task=%s', (row['item_id'], a.task)).fetchone():
                skipped.append({'item_id': row['item_id'], 'invalid': bad or 'UNKNOWN_ITEM'})
                continue
            if a.task == 'ocr_region' and label.get('gold_text'):
                label['gold_text'] = unicodedata.normalize('NFC', label['gold_text'])
            db.execute('''INSERT INTO editor_eval.labels(item_id,annotator,label) VALUES (%s,%s,%s)
                          ON CONFLICT (item_id,annotator) DO UPDATE SET label=EXCLUDED.label, created_at=now()''',
                       (row['item_id'], a.annotator, Jsonb(label)))
            stored += 1
    print(json.dumps({'stored': stored, 'skipped': skipped[:20], 'skipped_count': len(skipped)}, ensure_ascii=False))


# ---- candidate outputs: recorded evidence -> (item, decision, score, raw) ----

def outputs(task, method, evidence):
    if task == 'speech_boundary' and method == 'model_logprob':
        for book, v in evidence['books'].items():
            for row in v['rows']:
                item = {'first': row['first'], 'second': row['second']}
                p = row['p']
                yield item, {'A': 'CONTINUES', 'B': 'ENDS', 'C': 'UNCERTAIN'}[max(p, key=p.get)], p['A'], row
    elif task == 'ocr_region' and method == 'diacritic_witness':
        for r in evidence['released']:
            yield None, 'OBJECTION_VOID', None, r
    elif task == 'claim_faithfulness' and method == 'choice_logprob':
        for r in evidence['results']:
            yield {'claim_id': r['claim_id']}, None, r['p_same_subject'], r
    elif task == 'claim_faithfulness' and method == 'person_agreement':
        for r in evidence['results']:
            yield {'claim_id': r['claim_id']}, r['person']['status'], None, r['person']
    else:
        raise SystemExit('UNKNOWN_TASK_METHOD')


def resolve(db, task, probe, raw):
    """Find the item a candidate output belongs to without trusting output fields beyond identity."""
    if task == 'speech_boundary':
        return key(task, probe)
    if task == 'ocr_region':
        row = db.execute("SELECT id FROM editor_eval.items WHERE task=%s AND input->>'span_id'=%s", (task, raw['id'])).fetchone()
        return row and row['id']
    row = db.execute("SELECT id FROM editor_eval.items WHERE task=%s AND input->>'claim_id'=%s", (task, probe['claim_id'])).fetchone()
    return row and row['id']


def cmd_run(db, a):
    raw_bytes = Path(a.evidence).read_bytes()
    evidence = json.loads(raw_bytes)
    run_id = key(a.task, [a.method, a.version, hashlib.sha256(raw_bytes).hexdigest()])
    db.execute('''INSERT INTO editor_eval.candidate_runs(id,task,method,version,source_evidence,source_sha256)
                  VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (id) DO NOTHING''',
               (run_id, a.task, a.method, a.version, Path(a.evidence).name, hashlib.sha256(raw_bytes).hexdigest()))
    stored, missing = 0, 0
    for probe, decision, score, raw in outputs(a.task, a.method, evidence):
        item_id = resolve(db, a.task, probe, raw)
        if not item_id or not db.execute('SELECT 1 FROM editor_eval.items WHERE id=%s', (item_id,)).fetchone():
            missing += 1
            continue
        db.execute('''INSERT INTO editor_eval.candidate_outputs(run_id,item_id,decision,score,raw) VALUES (%s,%s,%s,%s,%s)
                      ON CONFLICT (run_id,item_id) DO NOTHING''', (run_id, item_id, decision, score, Jsonb(raw)))
        stored += 1
    print(json.dumps({'run_id': run_id, 'stored': stored, 'unmatched': missing}))


# ---- metrics ----

def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {'precision': p, 'recall': r, 'f1': f, 'tp': tp, 'fp': fp, 'fn': fn}


def kappa(pairs):
    if not pairs:
        return None
    cats = sorted({x for pair in pairs for x in pair})
    n = len(pairs)
    observed = sum(x == y for x, y in pairs) / n
    expected = sum((sum(x == c for x, _ in pairs) / n) * (sum(y == c for _, y in pairs) / n) for c in cats)
    return None if expected == 1 else (observed - expected) / (1 - expected)


def edit_distance(a, b):
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        previous, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (ca != cb))
    return row[-1]


DIACRITICS = set('çğıöşüÇĞİÖŞÜ')


def gold(db, task, label_set, field, annotators):
    rows = db.execute('''SELECT l.item_id, l.annotator, l.label, i.split FROM editor_eval.labels l
                         JOIN editor_eval.items i ON i.id=l.item_id WHERE i.task=%s AND i.label_set=%s''',
                      (task, label_set)).fetchall()
    by_item = {}
    for r in rows:
        if annotators and r['annotator'] not in annotators:
            continue
        by_item.setdefault(r['item_id'], {})[r['annotator']] = (r['label'], r['split'])
    primary, agreement = {}, []
    for item, labels in by_item.items():
        ordered = sorted(labels)
        value = labels[ordered[0]][0].get(field)
        if len(ordered) >= 2:
            agreement.append((value, labels[ordered[1]][0].get(field)))
        primary[item] = (labels[ordered[0]][0], labels[ordered[0]][1])
    return primary, kappa([p for p in agreement if all(p)])


def runs(db, task):
    return db.execute('SELECT id,method,version FROM editor_eval.candidate_runs WHERE task=%s ORDER BY created_at', (task,)).fetchall()


def run_outputs(db, run_id):
    return {r['item_id']: r for r in db.execute('SELECT item_id,decision,score FROM editor_eval.candidate_outputs WHERE run_id=%s', (run_id,))}


def calibrate(scored, positive_high, target_precision):
    """Choose on calibration items the lowest threshold whose precision >= target; report on test."""
    calib = [(s, y) for s, y, split in scored if split == 'calibration']
    best = None
    for t in sorted({round(s, 4) for s, _ in calib}):
        chosen = [y for s, y in calib if (s >= t if positive_high else s <= t)]
        if chosen and sum(chosen) / len(chosen) >= target_precision:
            best = t
            break
    if best is None:
        return {'threshold': None, 'reason': 'NO_THRESHOLD_REACHES_TARGET_ON_CALIBRATION'}
    test = [(s, y) for s, y, split in scored if split == 'test']
    chosen = [y for s, y in test if (s >= best if positive_high else s <= best)]
    return {'threshold': best, 'target_precision': target_precision,
            'test_items': len(test), 'test_decided': len(chosen),
            'test_precision': sum(chosen) / len(chosen) if chosen else None,
            'test_coverage': len(chosen) / len(test) if test else None}


def report_speech(db, a):
    labels, agree = gold(db, 'speech_boundary', a.set, 'boundary', a.annotator)
    out = {'labelled': len(labels), 'kappa': agree, 'methods': {}}
    for run in runs(db, 'speech_boundary'):
        o = run_outputs(db, run['id'])
        tp = fp = fn = false_split = false_merge = abstain = 0
        scored = []
        for item, (label, split) in labels.items():
            y = label.get('boundary')
            if y not in ('CONTINUES', 'ENDS'):
                continue
            d = o.get(item)
            if d is None or d['decision'] in (None, 'UNCERTAIN'):
                abstain += 1
            else:
                tp += d['decision'] == 'ENDS' and y == 'ENDS'
                fp += d['decision'] == 'ENDS' and y == 'CONTINUES'
                fn += d['decision'] == 'CONTINUES' and y == 'ENDS'
                false_split += d['decision'] == 'ENDS' and y == 'CONTINUES'
                false_merge += d['decision'] == 'CONTINUES' and y == 'ENDS'
            if d is not None and d['score'] is not None:
                scored.append((d['score'], y == 'CONTINUES', split))
        out['methods'][f"{run['method']}:{run['version']}"] = {
            'ends': prf(tp, fp, fn), 'false_split': false_split, 'false_merge': false_merge, 'abstained': abstain,
            'calibration_continues': calibrate(scored, True, a.target_precision) if scored else None}
    return out


def report_ocr(db, a):
    labels, agree = gold(db, 'ocr_region', a.set, 'error_class', a.annotator)
    items = {r['id']: r['input'] for r in db.execute("SELECT id,input FROM editor_eval.items WHERE task='ocr_region' AND label_set=%s", (a.set,))}
    out = {'labelled': len(labels), 'kappa_error_class': agree, 'readers': {}, 'methods': {}}
    per_reader = {}
    for item, (label, _) in labels.items():
        g = label.get('gold_text')
        if not g:
            continue
        for reader, text in items[item]['readers'].items():
            text = unicodedata.normalize('NFC', text)
            s = per_reader.setdefault(reader, {'chars': 0, 'char_errors': 0, 'words': 0, 'word_errors': 0,
                                               'diacritic_total': 0, 'diacritic_correct': 0, 'regions': 0})
            s['regions'] += 1
            s['chars'] += len(g)
            s['char_errors'] += edit_distance(text, g)
            s['words'] += len(g.split())
            s['word_errors'] += edit_distance(text.split(), g.split())
            aligned = len(text) == len(g)
            for i, ch in enumerate(g):
                if ch in DIACRITICS:
                    s['diacritic_total'] += 1
                    s['diacritic_correct'] += aligned and text[i] == ch
    for reader, s in per_reader.items():
        out['readers'][reader] = {'regions': s['regions'], 'cer': s['char_errors'] / s['chars'] if s['chars'] else None,
                                  'wer': s['word_errors'] / s['words'] if s['words'] else None,
                                  'diacritic_accuracy_same_length_only': s['diacritic_correct'] / s['diacritic_total'] if s['diacritic_total'] else None}
    for run in runs(db, 'ocr_region'):
        o = run_outputs(db, run['id'])
        decided = [i for i in labels if i in o]
        out['methods'][f"{run['method']}:{run['version']}"] = {
            'coverage': len(decided) / len(labels) if labels else None, 'decided': len(decided)}
    return out


def report_claims(db, a):
    labels, agree = gold(db, 'claim_faithfulness', a.set, 'verdict', a.annotator)
    out = {'labelled': len(labels), 'kappa': agree,
           'not_faithful': sum(l.get('verdict') == 'NOT_FAITHFUL' for l, _ in labels.values()), 'methods': {}}
    for run in runs(db, 'claim_faithfulness'):
        o = run_outputs(db, run['id'])
        caught = missed = false_alarm = abstain = 0
        scored = []
        for item, (label, split) in labels.items():
            y = label.get('verdict')
            if y not in ('FAITHFUL', 'NOT_FAITHFUL'):
                continue
            d = o.get(item)
            if d is None:
                abstain += 1
                continue
            flagged = d['decision'] in ('NEEDS_REVIEW', 'NOT_FAITHFUL') if d['decision'] else None
            if flagged is not None:
                caught += flagged and y == 'NOT_FAITHFUL'
                missed += (not flagged) and y == 'NOT_FAITHFUL'
                false_alarm += flagged and y == 'FAITHFUL'
            if d['score'] is not None:
                scored.append((d['score'], y == 'FAITHFUL', split))
        out['methods'][f"{run['method']}:{run['version']}"] = {
            'not_faithful': prf(caught, false_alarm, missed), 'silent_pass': missed, 'no_output': abstain,
            'calibration_faithful': calibrate(scored, True, a.target_precision) if scored else None}
    return out


REPORTS = {'speech_boundary': report_speech, 'ocr_region': report_ocr, 'claim_faithfulness': report_claims}


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    s = sub.add_parser('load'); s.add_argument('task', choices=TASKS); s.add_argument('evidence'); s.add_argument('--set', required=True); s.add_argument('--book')
    s = sub.add_parser('export'); s.add_argument('task', choices=TASKS); s.add_argument('out'); s.add_argument('--set', required=True)
    s = sub.add_parser('import'); s.add_argument('task', choices=TASKS); s.add_argument('csv'); s.add_argument('--annotator', required=True)
    s = sub.add_parser('run'); s.add_argument('task', choices=TASKS); s.add_argument('evidence'); s.add_argument('--method', required=True); s.add_argument('--version', required=True)
    s = sub.add_parser('report'); s.add_argument('task', choices=TASKS); s.add_argument('--set', required=True)
    s.add_argument('--annotator', action='append'); s.add_argument('--target-precision', type=float, default=0.97); s.add_argument('--json')
    a = p.parse_args()
    with connect() as db:
        if a.command == 'report':
            result = REPORTS[a.task](db, a)
            text = json.dumps(result, ensure_ascii=False, indent=1, default=lambda v: None if isinstance(v, float) and math.isnan(v) else v)
            if a.json:
                Path(a.json).write_text(text)
            print(text)
        else:
            {'init': cmd_init, 'load': cmd_load, 'export': cmd_export, 'import': cmd_import, 'run': cmd_run}[a.command](db, a)


if __name__ == '__main__':
    main()
