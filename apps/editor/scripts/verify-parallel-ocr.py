#!/usr/bin/env python3
"""Run on the real deployment host: API/PG, immutable OCR proof and overlap."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1];os.chdir(root)
gen=str(uuid.UUID(sys.argv[1]));page=int(sys.argv[2])
base=os.environ.get('EDITOR_VERIFY_BASE_URL','http://127.0.0.1:8810')
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=30) as r:return json.load(r)
def records(kind):
    result=[];offset=0
    while True:
        data=get(f'/v1/generations/{gen}/{kind}?pdf_page={page}&limit=100&offset={offset}')
        result+=data['items']
        if not data['has_more']:return result
        offset+=len(data['items'])
rows={k:records(k) for k in ('evidence','source_spans','page_readings','visual_observations','page_claims','page_checks')}
assert all(rows.values()),'PAGE_NOT_COMPLETE'
code="""import json,sys
from editor.config import connection,code_manifest
with connection() as db:
 rows=db.execute('SELECT kind,id,record_key,data FROM editor.records WHERE generation_id=%s AND data->>\'pdf_page\'=%s',(sys.argv[1],sys.argv[2])).fetchall()
print(json.dumps({'rows':rows,'code_manifest':code_manifest()},default=str))
"""
# SQL below uses parameter binding, independently of application API pagination.
code=code.replace("AND data->>'pdf_page'=%s", "AND data->>$$pdf_page$$=%s")
db=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,gen,str(page)]))
by_id={r['id']:r for r in db['rows']}
for kind,items in rows.items():
    for row in items:
        expected=by_id[row['id']]
        assert expected['kind']==kind and expected['record_key']==row['record_key'] and expected['data']==row['data'],'API_PG_MISMATCH'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
measurements=[];promoted=0
for row in rows['source_spans']:
    d=row['data'];m=d.get('ocr_vl_measurement')
    if not m:continue
    measurements.append(m)
    assert m['code_sha256']==db['code_manifest']['ocr_vl.py'],'OCR_CODE_MISMATCH'
    assert m['render_sha256']==d['render_sha256'] and m['bbox']==d['bbox'] and m['pdf_page']==page,'OCR_SCOPE_MISMATCH'
    assert sha(base64.b64decode(m['crop_image_base64'],validate=True))==m['crop_sha256'],'CROP_HASH_MISMATCH'
    raw=m['raw_response'].encode();assert sha(raw)==m['response_sha256'],'RAW_RESPONSE_MISMATCH'
    response=json.loads(raw);choice=response['choices'][0]
    assert choice['message']['content']==m['text'] and choice['finish_reason']==m['finish_reason'],'RAW_TEXT_MISMATCH'
    assert response['model']==m['model']=='paddleocr-vl-1.6','OCR_MODEL_MISMATCH'
    if d['selected_reader']=='PADDLEOCR_VL':
        promoted+=1
        assert d['status']=='TEXT_AGREED' and m['finish_reason']=='stop','INVALID_PROMOTION'
        assert d['ocr_vl_selection']['selected_text']==d['text'] and not d['ocr_vl_selection']['blockers'],'UNSUPPORTED_PROMOTION'
    assert m['eligible_for_synthesis'] is False
visuals=[o['metrics'] for r in rows['visual_observations'] for o in r['data']['observations']]
for m in visuals:
    assert m['model_name']=='qwen3.8-flash-next' and m['model_backend']=='vllm','MAIN_MODEL_MISMATCH'
    assert m['code_manifest']==db['code_manifest'],'VISUAL_CODE_MISMATCH'
claims=rows['page_claims'][0]['data']
assert claims['input_visual_descriptions'] is False
spans={r['id']:r['data'] for r in rows['source_spans']}
for c in claims['claims']:
    assert all(spans[r]['status']=='TEXT_AGREED' for r in c['span_refs'])
    assert c['eligible_for_synthesis'] is False
for r in rows['page_checks']:assert r['data']['semantic_acceptance'] is False
pairs=[{'ocr_start':m['started_at'],'ocr_end':m['finished_at'],'qwen_start':v['started_at'],'qwen_end':v['finished_at']}
       for m in measurements for v in visuals if max(m['started_at'],v['started_at'])<min(m['finished_at'],v['finished_at'])]
report={'generation_id':gen,'pdf_page':page,'api':base,'api_pg_match':True,
        'ocr_regions':len(measurements),'ocr_supported_promotions':promoted,'qwen_visual_calls':len(visuals),
        'overlapping_call_pairs':pairs,'parallel_overlap_observed':bool(pairs),
        'code_manifest':db['code_manifest'],'semantic_acceptance':False,'application_writes':0}
target=root/'evidence'/f'parallel-ocr-{gen}-page-{page:04}.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2));target.chmod(0o600)
print(json.dumps({k:v for k,v in report.items() if k not in ('code_manifest','overlapping_call_pairs')}))
