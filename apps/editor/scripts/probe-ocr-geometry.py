#!/usr/bin/env python3
"""Compare crop geometry on actual failed pages without changing any book record."""
import json,os,subprocess,sys,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/'evidence/source-spans-run.json').read_text());gen=run['generation_id']
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
code='''import base64,json,sys,httpx
from editor.book_store import ROOT,get_records,source_for,sha
from editor.source_pipeline import optical_verdict
gen,page=sys.argv[1],int(sys.argv[2]);source=source_for(gen)
evidence=next(r for r in get_records(gen,'evidence') if r['data']['pdf_page']==page)
spans=[r for r in get_records(gen,'source_spans') if r['data']['pdf_page']==page]
raw=(ROOT/source['sha256']/'ocr-regions-v2'/f'page-{page:04}.png').read_bytes()
assert sha(raw)==evidence['data']['ocr_render_sha256']
def key(box):return tuple(round(v,7) for v in box)
by_box={key(r['data']['bbox']):r for r in spans};assert len(by_box)==len(spans)
with httpx.Client(timeout=900,trust_env=False) as client:
 response=client.post('http://editor-ocr-geometry-pilot:8080/ocr',json={'image_base64':base64.b64encode(raw).decode(),'regional_pass':True,'regional_geometry':'compare-perspective-v1'})
 response.raise_for_status();reading=response.json()
assert reading['image_sha256']==sha(raw)
comparisons=[]
for line in reading['lines']:
 xs=[p[0] for p in line['polygon']];ys=[p[1] for p in line['polygon']]
 box=[min(xs)/reading['width'],min(ys)/reading['height'],(max(xs)-min(xs))/reading['width'],(max(ys)-min(ys))/reading['height']]
 old=by_box.get(key(box));candidate=line.get('perspective_candidate',{})
 if old is None or old['data']['raw_text']!=line['text'] or candidate.get('status')!='MEASUREMENT_ONLY':
  comparisons.append({'status':'UNMATCHED_MEASUREMENT','bbox':box});continue
 d=old['data'];common=(d['secondary_text'],d['pdf_text'],d['pdf_usable'],d.get('reread_measurement'))
 baseline=optical_verdict(line,*common)
 alternative=optical_verdict({**line,'region_text':candidate['text'],'region_score':candidate['score']},*common)
 comparisons.append({'source_span_id':str(old['id']),'bbox':box,'stored_status':d['status'],
  'baseline':baseline,'perspective':alternative,'raw_text':line['text'],
  'baseline_region_text':line['region_text'],'perspective_text':candidate['text'],
  'baseline_region_score':line['region_score'],'perspective_score':candidate['score']})
print(json.dumps({'evidence':evidence,'spans':spans,'reading':reading,'comparisons':comparisons},default=str,ensure_ascii=False))
'''
summaries=[]
for page in map(int,sys.argv[1:] or ['29','38']):
    if not 1<=page<=100:raise ValueError('INVALID_PAGE')
    url=f'http://127.0.0.1:8810/v1/generations/{gen}/evidence?pdf_page={page}&limit=100'
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as response:reference=json.load(response)['items'][0]
    result=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code,gen,str(page)],text=True))
    assert result['evidence']==reference,'API_PG_SOURCE_MISMATCH'
    valid=[r for r in result['comparisons'] if 'baseline' in r]
    summary={'page':page,'regions':len(result['comparisons']),'matched_measurements':len(valid),
      'baseline_vs_stored_status_drift':sum(r['baseline']['status']!=r['stored_status'] for r in valid),
      'baseline_agreed':sum(r['baseline']['status']=='TEXT_AGREED' for r in valid),
      'perspective_agreed':sum(r['perspective']['status']=='TEXT_AGREED' for r in valid),
      'improved':sum(r['baseline']['status']=='NEEDS_REVIEW' and r['perspective']['status']=='TEXT_AGREED' for r in valid),
      'regressed':sum(r['baseline']['status']=='TEXT_AGREED' and r['perspective']['status']=='NEEDS_REVIEW' for r in valid),
      'seconds':result['reading']['seconds'],'semantic_acceptance':False,'book_records_written':0}
    out=root/'evidence'/f'ocr-geometry-{gen}-page-{page:04}.json'
    with out.open('x') as stream:json.dump({'generation_id':gen,'summary':summary,**result},stream,ensure_ascii=False,indent=2)
    summaries.append(summary);print(json.dumps(summary),flush=True)
(root/'evidence/ocr-geometry-summary.json').write_text(json.dumps({'pages':summaries,'expected_answer_supplied':False,'production_ocr_changed':False},indent=2))
