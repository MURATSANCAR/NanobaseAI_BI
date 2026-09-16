#!/usr/bin/env python3
"""Compare candidate alignment code with immutable real API/PG and PDF artifacts.

Run on the connected server. No records, source files or review decisions change.
The report measures agreement, not transcription or literary accuracy.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
import urllib.request

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root/'backend'))
from editor.source_alignment import reader_text

run = json.loads((root/'evidence/source-spans-run.json').read_text())
gen = run['generation_id']
headers = {'Authorization': 'Bearer '+(root/'secrets/api_token').read_text().strip()}


def rows(kind):
    result = []
    while True:
        request = urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{gen}/{kind}?limit=100&offset={len(result)}', headers=headers)
        with urllib.request.urlopen(request, timeout=60) as response:
            page = json.load(response)
        result.extend(page['items'])
        if not page['has_more']:
            return result


def norm(value):
    value = re.sub(r'-\s*\n\s*', '', value)
    return ''.join(c for c in unicodedata.normalize('NFKC', value).replace('İ','i').replace('I','ı').lower() if c.isalnum())


evidence = {r['data']['pdf_page']: r for r in rows('evidence')}
readings = {r['data']['pdf_page']: r for r in rows('page_readings')}
spans = [r for r in rows('source_spans') if r['data']['pdf_page'] in readings]
# Independently compare exact immutable API records with the actual PostgreSQL.
query = "SELECT json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key) FROM editor.records WHERE generation_id='"+gen+"' AND kind='source_spans'"
db = json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query], text=True))
db = [r for r in db if r['data']['pdf_page'] in readings]
assert spans == db, 'API_DB_MISMATCH'
source_sha = next(iter(evidence.values()))['data']['source_sha256']
code = """import json,hashlib,pathlib,sys
root=pathlib.Path('/data/artifacts')/sys.argv[1]; result={}
for p in (root/'pdf-text-regions-v1').glob('*.json'):
 raw=p.read_bytes(); d=json.loads(raw)
 result[d['pdf_page']]={'document':d,'sha256':hashlib.sha256(raw).hexdigest()}
print(json.dumps(result))
"""
pdf = json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,source_sha], text=True))
pages = {}
details = []
for row in spans:
    d = row['data']; page = d['pdf_page']; artifact = pdf[str(page)]
    assert artifact['document']['source_sha256'] == source_sha
    assert artifact['sha256'] == d['pdf_artifact_sha256']
    secondary, secondary_words, _ = reader_text(d['bbox'], evidence[page]['data']['blocks'])
    native, native_words, usable = reader_text(d['bbox'], artifact['document']['lines'])
    primary_agrees = bool(norm(d['text'])) and norm(d['text']) == norm(d.get('region_text') or '')
    secondary_agrees = bool(norm(secondary)) and norm(secondary) == norm(d['text'])
    pdf_agrees = usable and bool(norm(native)) and norm(native) == norm(d['text'])
    conflict = (bool(norm(secondary)) and not secondary_agrees) or (usable and not pdf_agrees)
    status = 'TEXT_AGREED' if primary_agrees and (secondary_agrees or pdf_agrees) and not conflict and min(d['score'],d.get('region_score') or 0)>=.9 else 'NEEDS_REVIEW'
    p = pages.setdefault(page, {'page':page,'spans':0,'before_agreed':0,'after_agreed':0,'promoted':0,'demoted':0})
    p['spans'] += 1; p['before_agreed'] += d['status']=='TEXT_AGREED'; p['after_agreed'] += status=='TEXT_AGREED'
    p['promoted'] += d['status']!='TEXT_AGREED' and status=='TEXT_AGREED'
    p['demoted'] += d['status']=='TEXT_AGREED' and status!='TEXT_AGREED'
    details.append({'source_span_id':row['id'],'pdf_page':page,'bbox':d['bbox'], 'text':d['text'],
        'region_text':d['region_text'],'before':d['status'],'after':status,
        'pdf_before':d['pdf_text'],'pdf_after':native,'secondary_before':d['secondary_text'],
        'secondary_after':secondary,'pdf_words':native_words,'secondary_words':secondary_words})
report={'generation_id':gen,'api_db_equal':True,'source_sha256':source_sha,
    'alignment_code_sha256':hashlib.sha256((root/'backend/editor/source_alignment.py').read_bytes()).hexdigest(),
    'semantic_acceptance':False,'source_mutations':0,'pages':list(pages.values()),'details':details}
destination=root/'evidence/source-alignment-comparison.json'
destination.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in report.items() if k!='details'},ensure_ascii=False,indent=2))
