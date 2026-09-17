#!/usr/bin/env python3
"""Verify a real repeated generation preserves measurements and remaps claim refs."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request

root=Path(__file__).resolve().parents[1];os.chdir(root)
run=json.loads((root/'evidence/source-spans-run.json').read_text());gen=run['generation_id']
base=os.environ.get('EDITOR_VERIFY_BASE_URL','http://127.0.0.1:8810').rstrip('/')
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()}
def get(path):
    with urllib.request.urlopen(urllib.request.Request(base+'/v1'+path,headers=headers),timeout=60) as response:return json.load(response)
assert get('/jobs/'+run['job_id'])['status']=='COMPLETED','JOB_NOT_COMPLETE'
parent=get('/generations/'+gen)['manifest']['reuse_measurements_from']
api={}
for kind in ('source_spans','page_readings','page_claims','visual_observations','evidence'):
    api[kind]=[];offset=0
    while True:
        response=get(f'/generations/{gen}/{kind}?offset={offset}&limit=100')
        api[kind]+=response['items']
        if not response['has_more']:break
        offset+=len(response['items'])
code='''import json,sys
from editor.book_store import get_records,sha
r=json.load(sys.stdin);gen=r['generation'];parent=r['parent'];api=r['api']
current={k:get_records(gen,k) for k in api};old={k:get_records(parent,k) for k in api}
assert json.loads(json.dumps(current,default=str))==api,'API_PG_MISMATCH'
old_hash=sha(json.dumps(old,sort_keys=True,default=str).encode())
new_spans={s['record_key']:s for s in current['source_spans']};mapping={};inherited=0
new_evidence={s['record_key']:s for s in current['evidence']}
evidence_mapping={str(r['id']):str(new_evidence[r['record_key']]['id']) for r in old['evidence']}
for previous in old['source_spans']:
 row=new_spans[previous['record_key']];d=row['data'];p=previous['data']
 assert d['reused_source_span_id']==str(previous['id']) and d['reused_from_generation']==parent
 for key in ('text','raw_text','bbox','render_sha256','status','issues','reread_measurement','reread_provenance'):
  assert d.get(key)==p.get(key),(previous['record_key'],key)
 mapping[str(previous['id'])]=str(row['id']);inherited+=bool(d.get('reread_measurement'))
assert len(new_spans)==len(old['source_spans'])
old_pages={row['record_key']:row for row in old['page_readings']}
for row in current['page_readings']:
 assert row['data']['measurement_reused'] and row['data']['reused_from_generation']==parent
 for key in ('span_count','agreed_spans','review_spans','model_manifest','render_sha256'):
  assert row['data'][key]==old_pages[row['record_key']]['data'][key]
old_claims={row['record_key']:row for row in old['page_claims']}
assert len(old_pages)==len(current['page_readings']) and len(old_claims)==len(current['page_claims'])
old_visuals={row['record_key']:row for row in old['visual_observations']}
assert len(old_visuals)==len(current['visual_observations'])
for row in current['visual_observations']:
 assert row['data']['reused_from_generation']==parent
 assert row['data']['reused_visual_observation_id']==str(old_visuals[row['record_key']]['id'])
for row in current['page_claims']:
 previous=old_claims[row['record_key']]
 assert row['data']['reused_claim_candidates_from']==str(previous['id'])
 assert row['data']['reused_from_generation']==parent
 for key in ('claims','blocked_claims'):
  expected=[{**c,'span_refs':[mapping[ref] for ref in c.get('span_refs',[])],
    'evidence_refs':[evidence_mapping[ref] for ref in c.get('evidence_refs',[])]} for c in previous['data'][key]]
  assert expected==row['data'][key],(row['record_key'],key)
assert old_hash==sha(json.dumps({k:get_records(parent,k) for k in api},sort_keys=True,default=str).encode())
print(json.dumps({'generation_id':gen,'parent':parent,'source_spans':len(new_spans),
 'inherited_rereads':inherited,'reused_claim_pages':len(current['page_claims']),
 'fresh_model_calls':0,'api_pg_equal':True,'parent_records_unchanged':True,'semantic_acceptance':False}))
'''
report=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],
    input=json.dumps({'generation':gen,'parent':parent,'api':api}),text=True))
(root/'evidence/measurement-lineage-verification.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
