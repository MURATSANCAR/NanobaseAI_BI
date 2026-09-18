#!/usr/bin/env python3
"""Run on the real deployment host: API/PG, immutable OCR proof and overlap."""
import base64
import hashlib
import json
import os
import re
import socket
import time
import urllib.error
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid
import unicodedata

root=Path(__file__).resolve().parents[1];os.chdir(root)
gen=str(uuid.UUID(sys.argv[1]));page=int(sys.argv[2])
base=os.environ.get('EDITOR_VERIFY_BASE_URL','http://127.0.0.1:8810')
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
def get(path):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(base+path,headers=headers),timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 502, 503, 504):
                raise
            reason = 'HTTP_' + str(error.code)
        except (urllib.error.URLError, ConnectionError, TimeoutError, socket.timeout) as error:
            reason = type(error).__name__
            cause = getattr(error, 'reason', error)
            if not isinstance(cause, (ConnectionError, TimeoutError, socket.timeout, socket.gaierror)):
                raise
        if attempt == 4:
            print('TRANSIENT_TRANSPORT_EXHAUSTED:' + reason, file=sys.stderr)
            raise SystemExit(75)
        time.sleep(min(8, 2 ** attempt))
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
 rows=db.execute('SELECT kind,id,record_key,data FROM editor.records WHERE generation_id=%s AND data->>$$pdf_page$$=%s',(sys.argv[1],sys.argv[2])).fetchall()
print(json.dumps({'rows':rows,'code_manifest':code_manifest()},default=str))
"""
# SQL below uses parameter binding, independently of application API pagination.
db=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,gen,str(page)]))
by_id={r['id']:r for r in db['rows']}
for kind,items in rows.items():
    for row in items:
        expected=by_id[row['id']]
        assert expected['kind']==kind and expected['record_key']==row['record_key'] and expected['data']==row['data'],'API_PG_MISMATCH'
sha=lambda raw:hashlib.sha256(raw).hexdigest()
measurements=[];promoted=0;skipped=0
for row in rows['source_spans']:
    d=row['data'];m=d.get('ocr_vl_measurement')
    if not m:
        route=d.get('ocr_vl_routing')
        if route and not route['request_ocr']:
            skipped+=1
            assert d['status']=='NEEDS_REVIEW' and route['changes_source_acceptance'] is False,'SKIPPED_SOURCE_PROMOTED'
        continue
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
        if d['ocr_vl_selection'].get('superseded_readers'):
            assert d['ocr_vl_selection']['method']=='paddleocr-vl-region-v2'
            assert d['ocr_vl_selection']['superseded_readers']==['PPOCR_REGION']
            assert d['pdf_usable'] and d['pdf_matches'],'NATIVE_CONSENSUS_REQUIRED'
            reread=d['reread_measurement']
            assert reread['bbox']==d['bbox'] and {r['psm'] for r in reread['readings']}=={7,13}
            assert len(reread['readings'])==2
            # Independently compare complete token streams including punctuation;
            # do not invoke the production selection function as its own oracle.
            streams=[]
            for value in [d['text'],d['pdf_text'],*[r['text'] for r in reread['readings']]]:
                assert not any(unicodedata.category(c) in ('Co','Cs') or c=='\ufffd' for c in value)
                normalized=unicodedata.normalize('NFKC',value).replace('İ','i').replace('I','ı').lower()
                normalized=normalized.translate(str.maketrans({'“':'"','”':'"','‘':"'",'’':"'"}))
                streams.append(re.findall(r'\w+|[^\w\s]',normalized))
            assert streams[0] and all(s==streams[0] for s in streams),'NATIVE_CROP_PUNCTUATION_CONFLICT'
    assert m['eligible_for_synthesis'] is False
visuals=[];fresh_visuals=[]
for r in rows['visual_observations']:
    for o in r['data']['observations']:
        m=o['metrics'];visuals.append(m)
        assert m['model_name']=='qwen3.8-flash-next' and m['model_backend']=='vllm','MAIN_MODEL_MISMATCH'
        origin=o.get('reused_from_generation') or r['data'].get('reused_from_generation')
        expected=db['code_manifest']
        seen=set()
        while origin:
            assert origin not in seen and len(seen)<100,'VISUAL_PROVENANCE_CYCLE'
            seen.add(origin)
            expected=get('/v1/generations/'+origin)['manifest']['code_manifest']
            if m['code_manifest']==expected:break
            prior=get(f'/v1/generations/{origin}/visual_observations?pdf_page={page}&limit=100')['items']
            assert len(prior)==1,'VISUAL_ORIGIN_MISSING'
            matches=[x for x in prior[0]['data']['observations'] if x['metrics']==m and x['crop_sha256']==o['crop_sha256']]
            assert len(matches)==1,'VISUAL_ORIGIN_CONTENT_MISMATCH'
            origin=matches[0].get('reused_from_generation') or prior[0]['data'].get('reused_from_generation')
        assert m['code_manifest']==expected,'VISUAL_CODE_MISMATCH'
        if not seen:fresh_visuals.append(m)
claims=rows['page_claims'][0]['data']
assert claims['input_visual_descriptions'] is False
spans={r['id']:r['data'] for r in rows['source_spans']}
for c in claims['claims']:
    assert all(spans[r]['status']=='TEXT_AGREED' for r in c['span_refs'])
    assert c['eligible_for_synthesis'] is False
for r in rows['page_checks']:assert r['data']['semantic_acceptance'] is False
pairs=[{'ocr_start':m['started_at'],'ocr_end':m['finished_at'],'qwen_start':v['started_at'],'qwen_end':v['finished_at']}
       for m in measurements for v in fresh_visuals if max(m['started_at'],v['started_at'])<min(m['finished_at'],v['finished_at'])]
review=get(f'/v1/generations/{gen}/source-review?pdf_page={page}')
shown={r['span_id']:r.get('ocr_vl') for p in review['pages'] for r in p['regions']}
for row in rows['source_spans']:
    m=row['data'].get('ocr_vl_measurement')
    if m and row['data']['status']!='TEXT_AGREED':
        assert shown.get(row['id']) and shown[row['id']]['text']==m['text'],'REVIEW_OCR_NOT_EXPOSED'
report={'generation_id':gen,'pdf_page':page,'api':base,'api_pg_match':True,
        'ocr_regions':len(measurements),'ocr_skipped_regions':skipped,'ocr_supported_promotions':promoted,'qwen_visual_calls':len(fresh_visuals),'qwen_visual_observations':len(visuals),
        'overlapping_call_pairs':pairs,'parallel_overlap_observed':bool(pairs),
        'code_manifest':db['code_manifest'],'semantic_acceptance':False,'application_writes':0}
target=root/'evidence'/f'parallel-ocr-{gen}-page-{page:04}.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2));target.chmod(0o600)
print(json.dumps({k:v for k,v in report.items() if k not in ('code_manifest','overlapping_call_pairs')}))
