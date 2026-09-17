#!/usr/bin/env python3
"""Bounded real-source pilot; keeps OCR candidates outside accepted book data."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/'evidence/source-spans-v2-final-run.json').read_text())
gen=run['generation_id']
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
rows=[]
for page in (29,38):
    offset=0
    while True:
        url=f'http://127.0.0.1:8810/v1/generations/{gen}/source_spans?pdf_page={page}&offset={offset}&limit=100'
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as response:
            result=json.load(response)
        rows.extend(result['items'])
        if not result['has_more']:break
        offset+=len(result['items'])
code="""import json,sys
from editor.book_store import get_records,source_for
gen=sys.argv[1]
print(json.dumps({'rows':[r for r in get_records(gen,'source_spans') if r['data']['pdf_page'] in (29,38)],'source':source_for(gen)},default=str))
"""
reference=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,gen],text=True))
assert sorted(rows,key=lambda r:r['id'])==sorted(reference['rows'],key=lambda r:r['id']),'API_PG_MISMATCH'
requests=[]
for page in (29,38):
    selected=[r for r in rows if r['data']['pdf_page']==page and r['data']['status']!='TEXT_AGREED']
    if selected:
        requests.append({'generation_id':gen,'source_sha256':reference['source']['sha256'],
            'pdf_page':page,'render_sha256':selected[0]['data']['render_sha256'],'spans':selected})
assert 0<sum(len(r['spans']) for r in requests)<=32,'PILOT_LIMIT'
(root/'evidence/ocr-vl-pilot-input.json').write_text(json.dumps(requests))
print(json.dumps({'generation_id':gen,'pages':[r['pdf_page'] for r in requests],
    'regions':sum(len(r['spans']) for r in requests),'api_pg_equal':True}),flush=True)
container='editor-ocr-vl-pilot-'+uuid.uuid4().hex[:12]
try:
    subprocess.run(['docker','compose','-f','compose.yaml','-f','compose.ocr-vl.yaml','--profile','ocr-vl',
        'run','--name',container,'--rm','--no-deps','-T','ocr-vl'],
        input=json.dumps(requests),text=True,check=True,timeout=3600)
finally:
    # Killing the Compose client alone would leave CPU work running after timeout.
    subprocess.run(['docker','rm','-f',container],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
