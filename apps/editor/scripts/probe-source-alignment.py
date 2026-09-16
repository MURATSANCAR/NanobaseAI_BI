#!/usr/bin/env python3
"""Actual page API/PG/artifact + deployed OCR + word-alignment diagnostic.

No expected book answer, no changed source/claim/review. Run when OCR is idle;
do not run beside an uncached page-reading step.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1];os.chdir(root)
gen=str(uuid.UUID(sys.argv[1]));page=int(sys.argv[2]);assert page>0
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
req=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{gen}/evidence?pdf_page={page}&limit=100',headers=headers)
with urllib.request.urlopen(req,timeout=30) as response:record=json.load(response)['items'][0]
code='''import base64,json,sys,httpx
from editor.book_store import get_records,source_for,ROOT,sha
from editor.source_pipeline import norm,negation
from editor.source_alignment import reader_text
gen,page=sys.argv[1],int(sys.argv[2])
record=next(r for r in get_records(gen,'evidence') if r['data']['pdf_page']==page)
source=source_for(gen);root=ROOT/source['sha256'];d=record['data']
raw=(root/'ocr-regions-v2'/f'page-{page:04}.png').read_bytes()
assert sha(raw)==d['ocr_render_sha256']
pdf_path=root/'pdf-text-regions-v1'/f'page-{page:04}.json'
pdf=json.loads(pdf_path.read_text());assert pdf['source_sha256']==source['sha256']
with httpx.Client(timeout=600,trust_env=False) as client:
 response=client.post('http://ocr:8080/ocr',json={'image_base64':base64.b64encode(raw).decode(),'regional_pass':True})
 response.raise_for_status();reading=response.json()
assert reading['image_sha256']==sha(raw)
spans=[]
for line in reading['lines']:
 xs=[p[0] for p in line['polygon']];ys=[p[1] for p in line['polygon']]
 box=[min(xs)/reading['width'],min(ys)/reading['height'],(max(xs)-min(xs))/reading['width'],(max(ys)-min(ys))/reading['height']]
 secondary,_,_=reader_text(box,d['blocks']);native,words,usable=reader_text(box,pdf['lines'])
 primary=bool(norm(line['text'])) and norm(line['text'])==norm(line.get('region_text',''))
 second=bool(norm(secondary)) and norm(secondary)==norm(line['text'])
 native_agrees=usable and bool(norm(native)) and norm(native)==norm(line['text'])
 conflict=(bool(norm(secondary)) and not second) or (usable and not native_agrees)
 agreed=primary and (second or native_agrees) and not conflict and min(line['score'],line.get('region_score',0))>=.9
 spans.append({'text':line['text'],'region_text':line.get('region_text'),'bbox':box,'secondary':secondary,'native_pdf':native,
  'pdf_words':words,'status':'TEXT_AGREED' if agreed else 'NEEDS_REVIEW','negation_tokens':negation(line['text'])})
print(json.dumps({'record':record,'reading':reading,'spans':spans,'pdf_sha256':sha(pdf_path.read_bytes())},default=str,ensure_ascii=False))
'''
result=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,gen,str(page)],text=True))
assert result['record']==record,'API_DB_SOURCE_MISMATCH'
report={'generation_id':gen,'pdf_page':page,'application_writes':0,'expected_answer_supplied':False,
    'api_db_source_equal':True,'semantic_acceptance':False,**result}
path=root/'evidence'/f'source-alignment-page-{page:04}-{gen}.json'
with path.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
print(json.dumps({'evidence':str(path),'regions':len(result['spans']),
    'agreed':sum(s['status']=='TEXT_AGREED' for s in result['spans']),
    'negated_regions':[{'status':s['status'],'negation_tokens':s['negation_tokens']} for s in result['spans'] if s['negation_tokens']],
    'seconds':result['reading']['seconds'],'application_writes':0,'semantic_acceptance':False},ensure_ascii=False))
