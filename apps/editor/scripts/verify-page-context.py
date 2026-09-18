#!/usr/bin/env python3
"""Real deployment-only source context probe. No application data writes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import uuid

p=argparse.ArgumentParser()
p.add_argument('generation');p.add_argument('--page',type=int,required=True)
p.add_argument('--module',required=True);p.add_argument('--fragment-artifact')
p.add_argument('--persisted-fragments',action='store_true')
p.add_argument('--root',default='/data/nanobaseai/editor');args=p.parse_args()
root=Path(args.root);gen=str(uuid.UUID(args.generation));module=Path(args.module).read_bytes()
if args.persisted_fragments and args.fragment_artifact:raise SystemExit('Choose persisted fragments or a component artifact')
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def get_rows(kind,page):
    rows=[];offset=0
    while True:
        request=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{gen}/{kind}?pdf_page={page}&limit=100&offset={offset}',headers=headers)
        with urllib.request.urlopen(request,timeout=30) as response:data=json.load(response)
        rows+=data['items']
        if not data['has_more']:return rows
        offset+=len(data['items'])
pages=range(max(1,args.page-1),args.page+2);kinds=('evidence','layout_regions','source_spans')
if args.persisted_fragments:kinds+=('source_fragments',)
rows={page:{kind:get_rows(kind,page) for kind in kinds} for page in pages}
code="import json,sys; from editor.config import connection; p=json.load(sys.stdin); db=connection(); c=db.__enter__(); rows=c.execute('SELECT id,kind,record_key,data FROM editor.records WHERE generation_id=%s AND kind=ANY(%s) AND (data->>%s)::int=ANY(%s)',(p['generation'],p['kinds'],'pdf_page',p['pages'])).fetchall(); print(json.dumps(rows,default=str))"
payload={'generation':gen,'kinds':list(kinds),'pages':list(pages)}
raw=subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],input=json.dumps(payload).encode(),cwd=root)
pg={r['id']:r for r in json.loads(raw)}
count=0
for page in pages:
    for kind in kinds:
        for row in rows[page][kind]:
            expected=pg[row['id']]
            assert expected['kind']==kind and expected['data']==row['data'] and expected['record_key']==row['record_key'],'API_PG_MISMATCH'
            count+=1
fragments=[row for page in pages for row in rows[page].get('source_fragments',[])];fragment_sha=None;fragment_id_projection=[]
if args.fragment_artifact:
    artifact_raw=Path(args.fragment_artifact).read_bytes();artifact=json.loads(artifact_raw)
    fragment_sha=hashlib.sha256(artifact_raw).hexdigest()
    assert artifact['generation_id']==gen and artifact['application_writes']==0,'FRAGMENT_SCOPE_MISMATCH'
    for fragment in artifact['fragments']:
        d=fragment['data'];parent=pg[d['parent_source_span_id']]['data']
        assert d['parent_record_sha256']==digest(parent),'FRAGMENT_PARENT_HASH_MISMATCH'
        assert parent['status']=='NEEDS_REVIEW' and parent['render_sha256']==d['render_sha256'] and parent['pdf_page']==d['pdf_page'],'FRAGMENT_SOURCE_MISMATCH'
        x,y,w,h=d['bbox'];px,py,pw,ph=parent['bbox']
        assert x>=px and y>=py and x+w<=px+pw+1e-9 and y+h<=py+ph+1e-9,'FRAGMENT_BBOX_MISMATCH'
        parent_row=pg[d['parent_source_span_id']]
        bbox_hash=hashlib.sha256(json.dumps(d['bbox'],separators=(',',':')).encode()).hexdigest()[:16]
        key=parent_row['record_key']+'-fragment-'+bbox_hash
        projected_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'editor:'+':'.join((gen,'source_fragments',key))))
        fragment_id_projection.append({'measurement_identity':fragment['id'],'record_key':key,
                                       'projected_record_id':projected_id,'persisted':False})
        fragments.append({'id':projected_id,'record_key':key,'data':d})
bundles=[];omitted=[]
for page in pages:
    source=rows[page]
    if len(source['evidence'])!=1 or len(source['layout_regions'])!=1 or not source['source_spans']:
        omitted.append({'pdf_page':page,'reason':'SOURCE_PAGE_NOT_COMPLETE'});continue
    bundles.append({'evidence':source['evidence'][0],'layout':source['layout_regions'][0]['data'],
                    'spans':source['source_spans'],'fragments':[f for f in fragments if f['data']['pdf_page']==page]})
assert any(b['evidence']['data']['pdf_page']==args.page for b in bundles),'TARGET_NOT_READY'
tail="\nfrom editor.analysis import model\nbundles=json.loads("+repr(json.dumps(bundles))+ ")\nprint(json.dumps(classify("+str(args.page)+",bundles,model),ensure_ascii=False))\n"
result=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',
    'import sys; exec(compile(sys.stdin.read(),"page_context_candidate.py","exec"))'],input=module+tail.encode(),cwd=root))
report={'generation_id':gen,'target_page':args.page,'api_pg_rows_matched':count,'fragment_artifact_sha256':fragment_sha,
        'persisted_fragments':args.persisted_fragments,
        'fragment_parent_hashes_verified':len(fragments),'module_sha256':hashlib.sha256(module).hexdigest(),
        'fragment_record_id_projection':fragment_id_projection,
        'input_bundles_sha256':digest(bundles),'omitted_incomplete_pages':omitted,'result':result,
        'application_writes':0,'semantic_acceptance':False,'expected_role_supplied':False}
path=root/'evidence'/('page-context-'+gen+'-%04d-'%args.page+report['module_sha256'][:12]+'-'+report['input_bundles_sha256'][:12]+'.json')
with path.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
print(json.dumps({'evidence':str(path),'api_pg_rows_matched':count,'fragment_parent_hashes_verified':len(fragments),
                  'page_role':result['page_role'],'eligible_for_identity_context':result['eligible_for_identity_context'],
                  'reason':result['reason'],'semantic_acceptance':False},ensure_ascii=False))
