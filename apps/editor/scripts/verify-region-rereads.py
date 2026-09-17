#!/usr/bin/env python3
"""Accept real reread API/artifact provenance; never accept semantic claims."""
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/'evidence/source-spans-run.json').read_text())
gen=str(uuid.UUID(run['generation_id']))
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
base=f'http://127.0.0.1:8810/v1/generations/{gen}/region-rereads'
try:
    urllib.request.urlopen(base,timeout=60)
    raise AssertionError('UNAUTHENTICATED_REREAD_ACCESS')
except urllib.error.HTTPError as exc:
    assert exc.code==401
with urllib.request.urlopen(urllib.request.Request(
    base,headers=headers),timeout=60) as response:
    actual=json.load(response)
query="SELECT json_agg(json_build_object('id',id,'data',data)) FROM editor.records WHERE generation_id='"+gen+"' AND kind='source_spans' AND data->>'status'='NEEDS_REVIEW'"
db=json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True))
expected={r['id']:r['data'] for r in db};seen=set();checks=[]
for page in actual['items']:
    assert page['generation_id']==gen and not page['semantic_acceptance']
    code="""import json,sys,hashlib
from editor.book_store import ROOT,source_for
gen,page=sys.argv[1],int(sys.argv[2]);source=source_for(gen);root=ROOT/source['sha256']
data=json.loads((root/'region-reread-v1'/gen/f'page-{page:04}.json').read_text())
assert hashlib.sha256((root/'ocr-regions-v2'/f'page-{page:04}.png').read_bytes()).hexdigest()==data['render_sha256']
print(json.dumps(data))
"""
    artifact=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,gen,str(page['pdf_page'])],text=True))
    assert page==artifact,'API_ARTIFACT_MISMATCH'
    with urllib.request.urlopen(urllib.request.Request(base+'?pdf_page='+str(page['pdf_page']),headers=headers),timeout=60) as response:
        assert json.load(response)['items']==[page],'PAGE_FILTER_MISMATCH'
    for region in page['regions']:
        sid=region['source_span_id'];assert sid not in seen;seen.add(sid)
        old=expected[sid]
        assert old['bbox']==region['bbox'] and old['pdf_page']==page['pdf_page']
        assert old['render_sha256']==page['render_sha256']
        assert not region['eligible_for_synthesis']
        assert [r['psm'] for r in region['readings']]==[7,13]
    checks.append({'page':page['pdf_page'],'api_artifact_pg_equal':True,'regions':len(page['regions'])})
    if len(checks)%10==0:print(json.dumps({'verified_pages':len(checks),'failed':0}),flush=True)
assert seen==set(expected),'INCOMPLETE_REREAD_COVERAGE'
with urllib.request.urlopen(urllib.request.Request(
    f'http://127.0.0.1:8810/v1/generations/{gen}/source-review',headers=headers),timeout=60) as response:
    review=json.load(response)
review_regions=[r for page in review['pages'] for r in page['regions']]
assert {r['span_id'] for r in review_regions}==seen
assert all(r['next_action']=='RECONCILE_READER_EVIDENCE' and r.get('reread') for r in review_regions)
result={'generation_id':gen,'regions':len(seen),'checks':checks,
        'api_artifact_pg_equal':True,'review_api_linked':True,'semantic_acceptance':False}
(root/'evidence/region-reread-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'verified_pages':len(checks),'regions':len(seen),'api_artifact_pg_equal':True,'semantic_acceptance':False}),flush=True)
