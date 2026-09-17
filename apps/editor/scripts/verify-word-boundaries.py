#!/usr/bin/env python3
"""Real API/PG regression: lexical boundaries must survive optical comparison."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid

root = Path(__file__).resolve().parents[1]
os.chdir(root)
generation = str(uuid.UUID(json.loads((root/'evidence/source-spans-run.json').read_text())['generation_id']))
headers = {'Authorization': 'Bearer '+(root/'secrets/api_token').read_text().strip()}
rows = []
while True:
    request = urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}/source_spans?offset={len(rows)}&limit=100', headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        batch = json.load(response)
    rows.extend(batch['items'])
    if not batch['has_more']:
        break
    assert batch['items'], 'EMPTY_PAGE'
query = f"SELECT json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key) FROM editor.records WHERE generation_id='{generation}' AND kind='source_spans'"
def database():
    return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query], text=True))
assert rows == database(), 'API_DB_MISMATCH'
code = '''import json,sys
from editor.source_pipeline import optical_verdict,VERSION
rows=json.load(sys.stdin)
print(json.dumps({'version':VERSION,'verdicts':[optical_verdict(r['data'],r['data']['secondary_text'],r['data']['pdf_text'],r['data']['pdf_usable'],r['data'].get('reread_measurement')) for r in rows]}))
'''
command = ['docker','compose','run','--rm','--no-deps','-T']
candidate = os.environ.get('EDITOR_BOUNDARY_CANDIDATE')
if candidate:
    command += ['-v', str(Path(candidate).resolve(strict=True))+':/app/editor/source_pipeline.py:ro']
command += ['--entrypoint','python','api','-c',code]
result = json.loads(subprocess.check_output(command,input=json.dumps(rows),text=True))
assert len(result['verdicts']) == len(rows)
# Independent lexical reference: scan Unicode letters/numbers into runs.
# Do not call the application's normalization or tokenization helpers.
import unicodedata
import re
def tokens(value):
    value = re.sub(r'-\s*\n\s*', '', value)
    value = unicodedata.normalize('NFKC',value).replace('İ','i').replace('I','ı').lower()
    runs=[]; word=''
    for char in value:
        if char.isalnum():
            word += char
        elif word:
            runs.append(word); word=''
    if word: runs.append(word)
    return runs
changes=[]; old_agreed=0; new_agreed=0
for row, verdict in zip(rows,result['verdicts']):
    d=row['data']; old_agreed += d['status']=='TEXT_AGREED'; new_agreed += verdict['status']=='TEXT_AGREED'
    a=tokens(d['text']); b=tokens(d.get('region_text') or '')
    c=tokens(d['secondary_text']); p=tokens(d['pdf_text'])
    if verdict['status']=='TEXT_AGREED':
        assert a and a==b, 'REGIONAL_BOUNDARIES_LOST'
        assert (c==a or (d['pdf_usable'] and p==a)), 'NO_INDEPENDENT_READER'
        assert not c or c==a, 'SECONDARY_BOUNDARIES_LOST'
        assert not d['pdf_usable'] or p==a, 'PDF_BOUNDARIES_LOST'
    if verdict['status'] != d['status']:
        assert verdict['status']=='NEEDS_REVIEW', 'UNEXPECTED_PROMOTION'
        changes.append({'id':row['id'],'page':d['pdf_page'],'before':d['status'],'after':verdict['status'],'issues':verdict['issues']})
assert rows==database(), 'SOURCE_RECORDS_CHANGED'
report={'generation_id':generation,'version':result['version'],'api_pg_equal':True,'source_records_unchanged':True,
    'regions':len(rows),'old_agreed':old_agreed,'new_agreed':new_agreed,'review':len(rows)-new_agreed,
    'changes':changes,'semantic_acceptance':False,'candidate':bool(candidate),
    'code_sha256':hashlib.sha256(Path(candidate or root/'backend/editor/source_pipeline.py').read_bytes()).hexdigest()}
request=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}',headers=headers)
with urllib.request.urlopen(request,timeout=60) as response:
    metadata=json.load(response)
if metadata['manifest']['pipeline_version']=='source-spans-v4':
    assert metadata['status']=='NEEDS_REVIEW', 'GENERATION_NOT_FINISHED'
    assert not changes, 'STORED_VERDICTS_DIFFER_FROM_DEPLOYED_CODE'
    parent=str(uuid.UUID(metadata['manifest']['reuse_measurements_from']))
    parent_query=query.replace(generation,parent)
    previous=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',parent_query],text=True))
    by_id={row['id']:row for row in previous}
    assert len(rows)==len(previous), 'REGION_COUNT_CHANGED'
    changed=[]
    for row in rows:
        d=row['data']; old=by_id[d['reused_source_span_id']]['data']
        assert d['reused_from_generation']==parent
        for field in ('text','raw_text','bbox','region_text','region_score','score','secondary_text','pdf_text','render_sha256','reread_measurement'):
            assert d[field]==old[field], 'RAW_MEASUREMENT_CHANGED:'+field
        if d['status']!=old['status']:
            changed.append(d['reused_source_span_id'])
    expected=json.loads((root/'evidence/word-boundaries-candidate.json').read_text())
    assert expected['generation_id']==parent
    assert sorted(changed)==sorted(row['id'] for row in expected['changes']), 'UNEXPECTED_GATE_CHANGES'
    report['new_generation_acceptance']={'parent':parent,'raw_measurements_unchanged':True,
        'expected_gate_changes':len(changed),'stored_verdicts_equal':True}
name='word-boundaries-candidate.json' if candidate else 'word-boundaries-deployed.json'
(root/'evidence'/name).write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
