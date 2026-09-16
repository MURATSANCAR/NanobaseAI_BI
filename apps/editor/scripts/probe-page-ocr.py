#!/usr/bin/env python3
"""Read an actual generation page through the API and compare independent OCR.

Run on the deployment host. No expected text and no application writes.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid
from reading_quality import assess_page_reading

root = Path(__file__).resolve().parents[1]
os.chdir(root)
generation = str(uuid.UUID(sys.argv[1])); page = int(sys.argv[2])
container = subprocess.check_output(['docker','compose','-f','compose.yaml','-f','compose.ocr.yaml','ps','-q','ocr'],text=True).strip()
image_id = subprocess.check_output(['docker','inspect',container,'--format','{{.Image}}'],text=True).strip()
base = os.environ.get('EDITOR_VERIFY_BASE_URL', 'http://127.0.0.1:8810')
headers = {'Authorization': 'Bearer ' + (root/'secrets/api_token').read_text().strip()}
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path, headers=headers), timeout=60) as r:
        return r.read()

def records(kind):
    found=[]; offset=0
    while True:
        data=json.loads(get(f'/v1/generations/{generation}/{kind}?limit=100&offset={offset}'))
        found.extend(data['items'])
        if not data['has_more']: return found
        offset += len(data['items'])

evidence = next(r for r in records('evidence') if r['data']['pdf_page']==page)
visual = next(r for r in records('visuals') if r['data']['pdf_page']==page)
raw = get('/v1/visuals/'+evidence['id'])
assert hashlib.sha256(raw).hexdigest() == evidence['data']['render_sha256']
# API container provides private network access; input is the exact authenticated API image.
code = '''import json,sys,urllib.request
body=sys.stdin.buffer.read()
request=urllib.request.Request('http://ocr:8080/ocr',data=body,headers={'Content-Type':'application/json'})
with urllib.request.urlopen(request,timeout=600) as r: print(r.read().decode())
'''
body = json.dumps({'image_base64':base64.b64encode(raw).decode(), 'regional_pass':True}).encode()
output = subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code], input=body)
result = json.loads(output)
assert result['image_sha256'] == evidence['data']['render_sha256']
source_code = '''import base64,json,sys
from editor.book_store import source_for,ROOT,get_records
gen,page=sys.argv[1],int(sys.argv[2]); source=source_for(gen)
record=next(r for r in get_records(gen,'evidence') if r['data']['pdf_page']==page)
path=ROOT/source['sha256']/'ocr-regions-v2'/f'page-{page:04}.png'
ocr= json.loads(path.with_suffix('.json').read_text())
print(json.dumps({'record_id':str(record['id']),'data':record['data'],
 'tesseract':ocr,'image_base64':base64.b64encode(path.read_bytes()).decode()}))
'''
source = json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',source_code,generation,str(page)]))
assert source['record_id'] == evidence['id'] and source['data'] == evidence['data'], 'API_DB_SOURCE_MISMATCH'
high_raw=base64.b64decode(source.pop('image_base64'))
assert hashlib.sha256(high_raw).hexdigest() == source['tesseract']['render_sha256']
high_body=json.dumps({'image_base64':base64.b64encode(high_raw).decode(),'regional_pass':True}).encode()
high_result=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],input=high_body))
assert high_result['image_sha256'] == source['tesseract']['render_sha256']
report = {'generation_id':generation, 'pdf_page':page, 'api':base,
          'ocr_image_id':image_id,
          'verification_scripts':{p:hashlib.sha256((root/'scripts'/p).read_bytes()).hexdigest()
             for p in ('probe-page-ocr.py','reading_quality.py')},
          'source_evidence':evidence, 'baseline_visual':visual, 'paddle':result,
          'paddle_2400':high_result, 'independent_db_source':source,
          'api_db_source_match':True,
          'reading_gate':assess_page_reading(visual['data']['description'], source['tesseract']['text'], high_result['lines']),
          'application_writes':0, 'expected_answer_supplied':False}
target = root/'evidence'/f'ocr-page-{page:04}-{generation}.json'
with target.open('x') as stream:
    target.chmod(0o600)
    json.dump(report, stream, ensure_ascii=False, indent=2)
print(json.dumps({'report':str(target), 'page':page, 'lines':len(result['lines']),
    'seconds':result['seconds'], 'seconds_2400':high_result['seconds'], 'application_writes':0,
    'disagreeing_regions':sum(r.get('reading_agrees') is False for r in result['lines'])}))
