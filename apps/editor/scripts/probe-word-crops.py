#!/usr/bin/env python3
"""Measure original real-book crops in a bounded, networkless OCR process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import uuid

root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/'evidence/source-spans-run.json').read_text())
gen=str(uuid.UUID(run['generation_id']))
pages=sorted(set(map(int,sys.argv[1:] or ['30','29','38'])))
assert pages and all(1<=page<=100 for page in pages)
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
export='''import json,sys
from editor.book_store import get_records,source_for
gen=sys.argv[1];pages=json.loads(sys.argv[2])
print(json.dumps({'source':source_for(gen),'evidence':[r for r in get_records(gen,'evidence') if r['data']['pdf_page'] in pages], 'spans':[r for r in get_records(gen,'source_spans') if r['data']['pdf_page'] in pages]},default=str))
'''
data=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',export,gen,json.dumps(pages)],text=True))
request={'source_sha256':data['source']['sha256'],'pages':[]}
for page in pages:
    evidence=next(r for r in data['evidence'] if r['data']['pdf_page']==page)
    for kind,expected in [('evidence',[evidence]),('source_spans',[r for r in data['spans'] if r['data']['pdf_page']==page])]:
        url=f'http://127.0.0.1:8810/v1/generations/{gen}/{kind}?pdf_page={page}&limit=100'
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=60) as response:actual=json.load(response)
        assert not actual['has_more'] and actual['items']==expected,'API_PG_MISMATCH'
    request['pages'].append({'page':page,'render_sha256':evidence['data']['ocr_render_sha256'],
        'regions':[{'id':r['id'],'word_boxes':[w['bbox'] for w in r['data']['secondary_word_regions']]} for r in data['spans'] if r['data']['pdf_page']==page]})
folder=root/'evidence'/('word-crops-'+str(uuid.uuid4()));folder.mkdir()
request_path=folder/'request.json';request_path.write_text(json.dumps(request))
config=json.loads(subprocess.check_output(['docker','compose','config','--format','json']))
image=config['services']['ocr']['image']
identity=json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]['Id']
container_name='editor-word-crops-'+folder.name.removeprefix('word-crops-')
command=['docker','run','--rm','--name',container_name,'--network','none','--read-only','--cap-drop','ALL','--cpus','4','--memory','4g',
    '--tmpfs','/tmp:rw,size=512m','-v',config['volumes']['artifacts']['name']+':/data/artifacts:ro',
    '-v',str(request_path)+':/request.json:ro','-v',str(root/'ocr/experiments/word_geometry_probe.py')+':/probe.py:ro',
    identity,'python','/probe.py']
try:
    with (folder/'ocr.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
finally:
    # Killing the Docker client on timeout does not necessarily stop its container.
    subprocess.run(['docker','rm','-f',container_name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
measurement=json.loads(next(line.removeprefix('MEASUREMENT_JSON:') for line in (folder/'ocr.log').read_text().splitlines() if line.startswith('MEASUREMENT_JSON:')))
evaluate='''import json,sys
from editor.source_pipeline import optical_verdict
data=json.load(sys.stdin); by_id={r['source_span_id']:r for r in data['measurement']['results']};out=[]
for row in data['spans']:
 d=row['data'];m=by_id[row['id']]
 if m['status']!='MEASUREMENT_ONLY':continue
 alternative=optical_verdict({'text':d['raw_text'],'score':d['score'],'region_text':m['text'],'region_score':m['score']},d['secondary_text'],d['pdf_text'],d['pdf_usable'],d.get('reread_measurement'))
 out.append({'page':d['pdf_page'],'id':row['id'],'baseline':d['status'],'alternative':alternative['status'],'issues':alternative['issues']})
print(json.dumps(out))
'''
comparisons=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',evaluate],input=json.dumps({**data,'measurement':measurement}),text=True))
summary={'generation_id':gen,'ocr_image_id':identity,'semantic_acceptance':False,'book_records_written':0,
    'seconds':measurement['seconds'],'pages':[{'page':page,
    'measured':sum(r['page']==page for r in comparisons),
    'improved':sum(r['page']==page and r['baseline']=='NEEDS_REVIEW' and r['alternative']=='TEXT_AGREED' for r in comparisons),
    'regressed':sum(r['page']==page and r['baseline']=='TEXT_AGREED' and r['alternative']=='NEEDS_REVIEW' for r in comparisons)} for page in pages]}
(folder/'report.json').write_text(json.dumps({'summary':summary,'measurement':measurement,'comparisons':comparisons},indent=2))
print(json.dumps({**summary,'evidence':str(folder)},indent=2))
