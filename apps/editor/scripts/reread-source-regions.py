#!/usr/bin/env python3
"""Run automatic region rereading on real API/PG measurements, on the server."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import uuid

root = Path(__file__).resolve().parents[1]; os.chdir(root)
lock = (root/'evidence/region-reread.lock').open('w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
run = json.loads((root/'evidence/source-spans-run.json').read_text())
gen = str(uuid.UUID(run['generation_id']))
selected = {int(p) for p in sys.argv[1:]}
headers = {'Authorization': 'Bearer '+(root/'secrets/api_token').read_text().strip()}


def sql(query):
    return json.loads(subprocess.check_output(['docker', 'compose', 'exec', '-T', 'postgres',
        'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query], text=True))


def api(kind):
    rows = []; offset = 0
    while True:
        url = f'http://127.0.0.1:8810/v1/generations/{gen}/{kind}?limit=100&offset={offset}'
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
            data = json.load(response)
        rows.extend(data['items'])
        if not data['has_more']:
            return rows
        offset += len(data['items'])


def fingerprint():
    return sql("SELECT to_json(md5(string_agg(id::text||data::text,'' ORDER BY id))) FROM editor.records WHERE generation_id='"+gen+"'")


assert sql("SELECT count(*) FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')") == 0, 'ACTIVE_ANALYSIS'
before = fingerprint()
spans = api('source_spans'); evidence = api('evidence')
for kind, rows in [('source_spans', spans), ('evidence', evidence)]:
    db = sql("SELECT json_agg(json_build_object('id',id,'record_key',record_key,'data',data) ORDER BY record_key) FROM editor.records WHERE generation_id='"+gen+"' AND kind='"+kind+"'")
    assert rows == db, 'API_PG_MISMATCH:'+kind
requests = []
for page in evidence:
    d = page['data']; number = d['pdf_page']
    if selected and number not in selected:
        continue
    targets = [r for r in spans if r['data']['pdf_page'] == number and r['data']['status'] == 'NEEDS_REVIEW']
    if targets:
        requests.append({'generation_id': gen, 'pdf_page': number,
                         'source_sha256': d['source_sha256'], 'render_sha256': d['ocr_render_sha256'],
                         'spans': targets})
checks = []
with tempfile.TemporaryFile(mode='w+') as stream:
    json.dump(requests, stream); stream.seek(0)
    proc = subprocess.Popen(['docker', 'compose', '--profile', 'tools', 'run', '--rm', '-T',
                            '--no-deps', '--entrypoint', 'python', 'document', '-m', 'editor.region_reread'],
                           stdin=stream, text=True, stdout=subprocess.PIPE)
    for line in proc.stdout:
        if line.startswith('{'):
            checks.append(json.loads(line))
            if len(checks) % 10 == 0:
                print(json.dumps({'reread_pages': len(checks), 'failed': 0,
                                  'semantic_acceptance': False}), flush=True)
    if proc.wait() != 0:
        raise RuntimeError('REREAD_FAILED_PARTIAL_ARTIFACTS_PRESERVED')
assert len(checks) == len(requests), 'INCOMPLETE_PAGE_REREADS'
assert before == fingerprint(), 'ORIGINAL_RECORDS_CHANGED'
report = {'generation_id': gen, 'api_pg_equal': True, 'original_records_unchanged': True,
          'pages': checks, 'regions': sum(c['regions'] for c in checks),
          'stable': sum(c['stable'] for c in checks),
          'supported_candidates': sum(c['supported_candidates'] for c in checks),
          'semantic_acceptance': False}
suffix = '-'.join(str(p) for p in sorted(selected)) or 'all'
(root/'evidence'/f'region-reread-{gen}-{suffix}.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report), flush=True)
