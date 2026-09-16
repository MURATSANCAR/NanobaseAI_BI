#!/usr/bin/env python3
"""Compare every real source image served by the API with its immutable hash."""
import hashlib
import json
from pathlib import Path
import urllib.request
import urllib.error

root=Path(__file__).resolve().parents[1]
run=json.loads((root/'evidence/reference-book-run.json').read_text())
gen=run['job']['generation_id']
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
base='http://127.0.0.1:8810'

def get(path):
    return urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=30)

with get(f'/v1/generations/{gen}/evidence?limit=100') as response: records=json.load(response)
assert not records['has_more'], 'Paginate before verifying a larger book'
assert records['total']==48, 'Reference book page count changed'
checks=[]
for row in records['items']:
    with get('/v1/visuals/'+row['id']) as response:
        raw=response.read()
        assert response.headers.get_content_type()=='image/png'
        assert response.headers.get('Cache-Control')=='no-store'
    actual=hashlib.sha256(raw).hexdigest()
    assert actual==row['data']['render_sha256'], 'API image does not match this source page'
    checks.append({'pdf_page':row['data']['pdf_page'],'evidence_id':row['id'],'sha256':actual,'bytes':len(raw)})
report={'generation_id':gen,'environment':'real remote Editor API',
        'verified_source_images':checks,'semantic_or_mobile_acceptance':False}
(root/'evidence'/('source-views-'+gen+'.json')).write_text(json.dumps(report,indent=2))
print(json.dumps({'generation_id':gen,'matched_images':len(checks),'no_store':True,
                  'semantic_or_mobile_acceptance':False}))
