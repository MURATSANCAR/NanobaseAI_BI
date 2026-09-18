#!/usr/bin/env python3
"""Independent remote-only acceptance of immutable real-source role probe artifacts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
import uuid
from source_role_reference import digest, verify_role_bindings

p=argparse.ArgumentParser();p.add_argument('artifact');p.add_argument('module');p.add_argument('--cited-module');a=p.parse_args()
assert sys.platform.startswith('linux') and os.environ.get('EDITOR_VERIFY_REMOTE_HOST')==socket.gethostname()
root=Path(os.environ['EDITOR_VERIFY_ROOT']);raw=Path(a.artifact).read_bytes();artifact=json.loads(raw)
role_hash=hashlib.sha256(Path(a.module).read_bytes()).hexdigest()
if a.cited_module:
 assert artifact['candidate_sha256']==hashlib.sha256(Path(a.cited_module).read_bytes()).hexdigest(), 'CITATION_CODE_CHANGED'
 assert artifact['support_module_sha256']['source_role_bindings']==role_hash, 'ROLE_CODE_CHANGED'
 projection_module=Path(a.module).with_name('role_reading_projection.py')
 assert artifact['support_module_sha256']['role_reading_projection']==hashlib.sha256(projection_module.read_bytes()).hexdigest(), 'PROJECTION_CODE_CHANGED'
else:
 assert artifact['candidate_sha256']==role_hash, 'CANDIDATE_CODE_CHANGED'
assert artifact['protected_before']==artifact['protected_after'] and artifact['application_writes']==0
assert artifact['api_pg_match'] is True and artifact['semantic_acceptance'] is False
generation=str(uuid.UUID(artifact['generation_id']));token=(root/'secrets/api_token').read_text().strip()
records={}
for kind in ('source_spans','source_passages'):
 rows=[]
 for page in artifact['pages']:
  offset=0
  while True:
   req=urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{generation}/{kind}?pdf_page={page}&limit=100&offset={offset}',headers={'Authorization':'Bearer '+token})
   with urllib.request.urlopen(req,timeout=180) as response:batch=json.load(response)
   rows.extend(batch['items']);offset+=len(batch['items'])
   if not batch['has_more']:break
   assert batch['items']
 records[kind]=rows
code="""
import json,sys
from editor.config import connection
p=json.load(sys.stdin)
with connection() as db:
 db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
 for kind,rows in p['records'].items():
  actual=db.execute("SELECT id,record_key,data FROM editor.records WHERE generation_id=%s AND kind=%s AND (data->>'pdf_page')::int=ANY(%s)",(p['generation'],kind,p['pages'])).fetchall()
  assert {str(r['id']):{'id':str(r['id']),'record_key':r['record_key'],'data':r['data']} for r in actual}=={r['id']:r for r in rows}
 protected={kind:db.execute("SELECT md5(string_agg(md5(row_to_json(r)::text),'' ORDER BY id)) AS hash FROM editor."+kind+" r WHERE generation_id=%s",(p['generation'],)).fetchone()['hash'] for kind in ('records','reviews')}
 print(json.dumps(protected))
"""
payload={'generation':generation,'pages':artifact['pages'],'records':records}
protected=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],cwd=root,input=json.dumps(payload).encode()))
assert protected==artifact['protected_after'], 'SOURCE_RECORDS_CHANGED'
passages={r['id']:r['data'] for r in records['source_passages']};spans={r['id']:r['data'] for r in records['source_spans']}
assert set(passages)=={r['passage_id'] for r in artifact['results']}
checked=[]
for row in artifact['results']:
 passage=passages[row['passage_id']];review=row['review']
 citation=review if a.cited_module else None
 assert digest(passage)==row['passage_sha256'] and passage['claim']==row['claim']
 regions=[{'span_id':ref,**{key:spans[ref][key] for key in ('text','bbox','render_sha256')}} for ref in passage['source_span_refs']]
 assert all(spans[ref]['status']=='TEXT_AGREED' and spans[ref]['role']=='TEXT' for ref in passage['source_span_refs'])
 if citation is not None:
  assert citation['version']=='source-semantic-review-v8-cited-support'
  assert citation['source_sha256']==digest(regions) and citation['source_regions']==regions
  assert citation['support_span_refs']==passage['source_span_refs']
  review=citation.get('role_binding_review')
  if review is None:
   assert citation['passed'] is False
   checked.append({'passage_id':row['passage_id'],'status':'EARLIER_GATE_REJECTED','reason':citation['reason']})
   continue
  assert citation['passed']==review['passed']
  assert review['reading_views']==citation['source_reading_segments']
  from source_qualification_reference import verify_qualification
  from source_obligation_reference import verify_obligations
  verify_qualification(passage['claim'],citation['source_reading_segments'],citation['qualification_gate'])
  verify_obligations(passage['claim'],regions,citation['obligation_review'])
  assert citation['metrics']['finish_reason']=='stop'
  assert citation['model_result']['checks']=={k:'PASS' for k in ('entailment','actor','speaker','polarity','narrative_mode','epistemic_strength')}
 assert review['claim_sha256']==digest(passage['claim']['text']) and review['source_sha256']==digest(regions)
 if review['passed']:
  verify_role_bindings(passage['claim'],regions,review)
  status='STRUCTURAL_PROOF_VERIFIED'
 elif review['reason']=='ROLE_PERSON_TRANSFER_UNPROVEN':
  source={m['id']:m for m in review['source_graph']['mentions']};target={m['id']:m for m in review['claim_graph']['mentions']}
  sc={c['id']:c for c in review['source_graph']['clauses']};cc={c['id']:c for c in review['claim_graph']['clauses']}
  conflicts=[]
  for binding in review['alignment']['bindings']:
   original=sc.get(binding['source_clause_id']);proposed=cc[binding['claim_clause_id']]
   sm=source.get(original['subject_id']) if original else None;tm=target.get(proposed['subject_id'])
   if sm and tm and sm['person'] in (1,2,3) and tm['person'] in (1,2,3) and sm['person']!=tm['person']:
    conflicts.append(binding)
  assert conflicts, 'PERSON_REJECTION_WITHOUT_GRAPH_CONFLICT'
  status='PERSON_CONFLICT_REJECTED'
 else:status='NEEDS_REVIEW'
 checked.append({'passage_id':row['passage_id'],'status':status,'reason':review['reason']})
report={'generation_id':generation,'artifact':str(Path(a.artifact).resolve()),'artifact_sha256':hashlib.sha256(raw).hexdigest(),
 'candidate_sha256':artifact['candidate_sha256'],'role_module_sha256':role_hash,'reference_sha256':hashlib.sha256(Path(__file__).with_name('source_role_reference.py').read_bytes()).hexdigest(),
 'reference_dependencies':{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('source_role_reference.py','role_projection_reference.py','source_qualification_reference.py','source_obligation_reference.py')},
 'api_pg_match':True,'protected_records_unchanged':True,'model_calls':0,'application_writes':0,'semantic_acceptance':False,'results':checked}
path=root/'evidence'/('role-binding-reference-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')
with path.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
path.chmod(0o600)
print(json.dumps({'evidence':str(path),'counts':{s:sum(r['status']==s for r in checked) for s in sorted({r['status'] for r in checked})},'semantic_acceptance':False}))
