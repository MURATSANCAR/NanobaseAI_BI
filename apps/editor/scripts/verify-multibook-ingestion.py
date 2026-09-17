#!/usr/bin/env python3
"""Upload unchanged real PDFs through the real API; compare PostgreSQL and Poppler.

Run on the deployed server only. This verifies ingestion, never semantic quality.
Checkpoints permit resuming long parser runs without duplicate uploads.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request
import uuid

p = argparse.ArgumentParser()
p.add_argument('pdf', type=Path)
p.add_argument('--title', required=True)
p.add_argument('--base', required=True)
p.add_argument('--wait-seconds', type=int, default=1800)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
os.chdir(root)
data = a.pdf.read_bytes()
digest = hashlib.sha256(data).hexdigest()
out = root / 'evidence/multibook-ingestion'
out.mkdir(parents=True, exist_ok=True)
record = out / (digest + '.json')
report = json.loads(record.read_text()) if record.exists() else {
    'source_sha256': digest, 'bytes': len(data), 'title': a.title,
    'api': a.base, 'run_id': str(uuid.uuid4()), 'semantic_acceptance': False,
    'analysis_started': False, 'status': 'STARTED'}
assert report['api'] == a.base and report['bytes'] == len(data)
token = (root / 'secrets/api_token').read_text().strip()

def save():
    record.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    record.with_suffix('.md').write_text(
        '# Gerçek kitap kaynak hazırlama\n\n' +
        '\n'.join(f'- {k}: {v}' for k, v in report.items()) +
        '\n\nYalnız yükleme/kaynak hazırlama kabulüdür; anlamsal analiz kabulü değildir.\n')

def api(method, path, body=None, key=None):
    headers = {'Authorization': 'Bearer ' + token}
    if key:
        headers['Idempotency-Key'] = report['run_id'] + ':' + key
    if isinstance(body, dict):
        body = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    with urllib.request.urlopen(urllib.request.Request(
            a.base.rstrip('/') + path, data=body, headers=headers, method=method), timeout=180) as r:
        return r.status, json.load(r)

def sql(query):
    return subprocess.check_output(['docker', 'compose', 'exec', '-T', 'postgres',
        'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query], text=True).strip()

try:
    save()
    if 'work_id' not in report:
        _, work = api('POST', '/v1/works', {'title': a.title}, 'work')
        report['work_id'] = work['id']; save()
    if 'edition_id' not in report:
        _, edition = api('POST', '/v1/editions',
            {'work_id': report['work_id'], 'label': 'Gerçek PDF kaynak kabulü'}, 'edition')
        report['edition_id'] = edition['id']; save()
    if 'upload_id' not in report:
        _, upload = api('POST', '/v1/editions/' + report['edition_id'] + '/uploads',
            {'expected_bytes': len(data), 'expected_sha256': digest}, 'upload')
        report['upload_id'] = upload['id']; report['upload_url'] = upload['upload_url']; save()
    _, status = api('GET', '/v1/uploads/' + report['upload_id'])
    if status['status'] == 'CREATED':
        api('PUT', report['upload_url'], data)
        _, status = api('GET', '/v1/uploads/' + report['upload_id'])
    if status['status'] == 'RECEIVED':
        api('POST', '/v1/uploads/' + report['upload_id'] + '/complete', {'confirm': True}, 'complete')
    deadline = time.monotonic() + a.wait_seconds
    while True:
        _, status = api('GET', '/v1/uploads/' + report['upload_id'])
        report['upload_status'] = status; report['status'] = status['status']; save()
        if status['status'] == 'COMPLETED':
            break
        if status['status'] not in ('PARSING', 'RECEIVED', 'CREATED'):
            raise RuntimeError('UPLOAD_TERMINAL_FAILURE: ' + json.dumps(status))
        if time.monotonic() >= deadline:
            print(json.dumps({'status': 'PENDING', 'evidence': str(record)}), flush=True)
            raise SystemExit(2)
        time.sleep(10)
    uid = str(uuid.UUID(report['upload_id']))
    db = json.loads(sql("SELECT json_build_object('status',u.status,'version',cv.id,'sha',cv.sha256,'manifest',s.manifest) FROM editor.uploads u JOIN editor.content_versions cv ON cv.id=u.content_version_id JOIN editor.source_probes s ON s.sha256=cv.sha256 WHERE u.id='" + uid + "'"))
    manifest = api('GET', '/v1/source-probes/' + digest)[1]
    assert manifest == db['manifest']
    assert db['status'] == status['status'] == 'COMPLETED'
    assert db['version'] == status['content_version_id'] and db['sha'] == digest
    original = '/data/artifacts/' + digest + '/original.pdf'
    info = subprocess.check_output(['docker', 'compose', 'exec', '-T', 'parser', 'pdfinfo', original], text=True)
    pages = int(re.search(r'^Pages:\s+(\d+)', info, re.M).group(1))
    stored_digest = subprocess.check_output(['docker', 'compose', 'exec', '-T', 'parser', 'sha256sum', original], text=True).split()[0]
    assert stored_digest == digest and manifest['bytes'] == len(data)
    assert pages == manifest['pdf_pages'] == len(manifest['pages'])
    assert [x['pdf_page'] for x in manifest['pages']] == list(range(1, pages + 1))
    assert manifest['source_accounting_complete']
    artifact_check = """import hashlib,json,sys
from pathlib import Path
m=json.load(sys.stdin); d=Path('/data/artifacts')/m['sha256']
def h(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert h(d/'docling.json')==m['docling_sha256']
for row in m['pages']:
 n=row['pdf_page']; assert h(d/f'page-{n:04}.png')==row['render_sha256']
 for sub in ('ocr-regions-v2','pdf-text-regions-v1'):
  r=json.loads((d/sub/f'page-{n:04}.json').read_text())
  assert r['source_sha256']==m['sha256'] and r['pdf_page']==n
  if sub=='ocr-regions-v2':
   assert h(d/sub/f'page-{n:04}.png')==r['render_sha256']
   assert h(d/sub/f'page-{n:04}.tsv')==r['raw_tsv_sha256']
print(json.dumps({'render_and_region_pages':len(m['pages']),'docling_hash_equal':True}))
"""
    artifacts = json.loads(subprocess.check_output(['docker', 'compose', 'exec', '-T',
        'parser', 'python', '-c', artifact_check], input=json.dumps(manifest), text=True))
    cv = str(uuid.UUID(db['version']))
    assert sql("SELECT count(*) FROM editor.generations WHERE content_version_id='" + cv + "'") == '0'
    report.update(status='PASS', content_version_id=cv, pdf_pages=pages,
        http_pg_manifest_equal=True, original_bytes_equal=True,
        independent_pdfinfo_pages_equal=True, generation_count=0,
        source_accounting_complete=True, artifact_checks=artifacts)
    save(); print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
except Exception as exc:
    report['status'] = 'FAILED'; report['error'] = str(exc); save()
    raise
