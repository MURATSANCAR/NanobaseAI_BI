#!/usr/bin/env python3
"""Compare offline OCR candidates with the real source API and immutable artifacts."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request

root=Path(__file__).resolve().parents[1];os.chdir(root)
requests=json.loads((root/'evidence/ocr-vl-pilot-input.json').read_text())
gen=requests[0]['generation_id']
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
for request in requests:
    url=f"http://127.0.0.1:8810/v1/generations/{gen}/source_spans?pdf_page={request['pdf_page']}&limit=100"
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as response:
        current=json.load(response)
    assert not current['has_more'],'PAGE_EXCEEDS_CHECK_LIMIT'
    mapping={row['id']:row for row in current['items']}
    assert all(mapping[row['id']]==row for row in request['spans']),'SOURCE_RECORD_CHANGED'
code='''import json,sys
from collections import Counter
from editor.book_store import ROOT,get_records,source_for,sha
from editor.source_pipeline import quote_tokens
requests=json.load(sys.stdin);gen=requests[0]['generation_id'];source=source_for(gen)
rows={r['id']:r for r in json.loads(json.dumps(get_records(gen,'source_spans'),default=str))};totals=Counter();results=[]
for request in requests:
 assert source['sha256']==request['source_sha256']
 for row in request['spans']:
  assert rows[row['id']]==row
  path=ROOT/source['sha256']/'ocr-vl-regions-v1'/gen/(row['id']+'.json')
  if not path.exists():totals['pending']+=1;continue
  raw=path.read_bytes();candidate=json.loads(raw);d=row['data']
  assert candidate['generation_id']==gen and candidate['source_span_id']==row['id']
  assert candidate['source_sha256']==source['sha256'] and candidate['render_sha256']==d['render_sha256']
  assert candidate['bbox']==d['bbox'] and candidate['pdf_page']==d['pdf_page']
  assert not candidate['eligible_for_synthesis'] and not candidate['expected_answer_supplied']
  assert candidate['prompt']=='OCR:'
  matches=[key for key in ('raw_text','region_text','secondary_text','pdf_text')
    if (key!='pdf_text' or d['pdf_usable']) and candidate['complete'] and quote_tokens(candidate['text'])
    and quote_tokens(candidate['text'])==quote_tokens(d.get(key) or '')]
  totals['processed']+=1;totals['complete']+=candidate['complete'];totals['matches_any_reader']+=bool(matches)
  totals['matches_paddle_and_tesseract']+=('raw_text' in matches and 'secondary_text' in matches)
  results.append({'span_id':row['id'],'page':d['pdf_page'],'complete':candidate['complete'],
    'matching_readers':matches,'seconds':candidate['seconds'],'tokens':candidate['tokens'],
    'artifact_sha256':sha(raw),'model_revision':candidate['model_manifest']['revision'],
    'code_sha256':candidate['code_sha256']})
print(json.dumps({'generation_id':gen,'totals':dict(totals),'regions':results,
 'api_pg_unchanged':True,'semantic_acceptance':False,'source_records_modified':False}))
'''
report=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],
    input=json.dumps(requests),text=True))
(root/'evidence/ocr-vl-pilot-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
