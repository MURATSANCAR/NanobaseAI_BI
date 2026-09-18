#!/usr/bin/env python3
"""Probe actual book figures on the deployment host, without changing records."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import uuid

p=argparse.ArgumentParser()
p.add_argument('generation');p.add_argument('--page',type=int,required=True)
p.add_argument('--figure',type=int,default=0);p.add_argument('--module',required=True)
args=p.parse_args();generation=str(uuid.UUID(args.generation))
root=Path(__file__).resolve().parents[1];module=Path(args.module).read_text()
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
records={}
for kind in ('evidence','visual_observations'):
    request=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}/{kind}?pdf_page={args.page}&limit=100',headers=headers)
    with urllib.request.urlopen(request,timeout=60) as response:batch=json.load(response)
    assert not batch['has_more'] and len(batch['items'])==1
    records[kind]=batch['items'][0]
code='''import base64,hashlib,httpx,json,sys,types
from editor.book_store import ROOT
from editor.config import connection
from editor.ocr_vl import crop_request
from editor.source_review import page_figures
from editor.analysis import model
p=json.load(sys.stdin)
with connection() as db:
 rows=db.execute("SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s AND id=ANY(%s::uuid[])",(p['generation'],[row['id'] for row in p['records'].values()])).fetchall()
assert len(rows)==2
for row in rows:
 expected=p['records'][row['kind']]
 assert str(row['id'])==expected['id'] and row['record_key']==expected['record_key'] and row['data']==expected['data'],'API_PG_MISMATCH'
evidence=p['records']['evidence']['data'];visual=p['records']['visual_observations']['data']
assert visual['evidence_refs']==[p['records']['evidence']['id']]
figures=page_figures(visual);figure=figures[p['figure']]
oi,fi=[int(part.split('-')[1]) for part in figure['figure_ref'].split('/')]
original=visual['observations'][oi]['figures'][fi]
candidate={k:original[k] for k in ('appearance','visible_action')}
raw=(ROOT/evidence['source_sha256']/('page-%04d.png'%evidence['pdf_page'])).read_bytes()
assert hashlib.sha256(raw).hexdigest()==evidence['render_sha256']
with httpx.Client(timeout=180,trust_env=False) as client:
 crop=crop_request(client,{'image_base64':base64.b64encode(raw).decode(),'bbox':figure['bbox']}).json()
assert crop['source_image_sha256']==evidence['render_sha256'] and crop['bbox']==figure['bbox']
module=types.ModuleType('visual_details_candidate');exec(compile(p['module'],'visual-details-candidate.py','exec'),module.__dict__)
result=module.review(crop,candidate,model)
print(json.dumps({'generation_id':p['generation'],'pdf_page':evidence['pdf_page'],'figure_ref':figure['figure_ref'],
 'figure_bbox':figure['bbox'],'source_render_sha256':evidence['render_sha256'],'original_candidate':candidate,
 'visual_record_id':p['records']['visual_observations']['id'],'result':result,'api_pg_match':True,
 'application_writes':0,'expected_eye_state_supplied':False,'semantic_acceptance':False}))
'''
payload={'generation':generation,'figure':args.figure,'records':records,'module':module}
raw=subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],cwd=root,input=json.dumps(payload).encode())
report=json.loads(raw);report['candidate_code_sha256']=hashlib.sha256(module.encode()).hexdigest()
target=root/'evidence'/('visual-details-'+generation+'-%04d-'%args.page+str(args.figure)+'-'+report['candidate_code_sha256'][:12]+'.json')
with target.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
target.chmod(0o600)
print(json.dumps({'evidence':str(target),'api_pg_match':True,'pdf_page':args.page,
 'measurement':report['result']['measurement'],'candidate_supported':report['result']['candidate_supported'],
 'reason':report['result']['reason'],'application_writes':0,'semantic_acceptance':False},ensure_ascii=False))
