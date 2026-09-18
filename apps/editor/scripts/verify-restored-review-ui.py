#!/usr/bin/env python3
"""Resume only real restored UI acceptance; retain prior failures and stop target."""
import os,json,pathlib,subprocess,time,urllib.request,hashlib,socket,uuid
assert socket.gethostname()==os.environ['EDITOR_VERIFY_REMOTE_HOST'] and os.name=='posix'
r=pathlib.Path(os.environ['EDITOR_VERIFY_ROOT']).resolve();t=pathlib.Path(os.environ['EDITOR_VERIFY_RESTORED_ROOT']).resolve()
assert t!=r and r not in t.parents,'RESTORED_ROOT_MUST_BE_SEPARATE'
os.chdir(t);generation=str(uuid.UUID(os.environ['EDITOR_VERIFY_GENERATION_ID']))
base=os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/');assert base.startswith('http://127.0.0.1:')
config=json.loads(subprocess.check_output(['docker','compose','config','--format','json'],text=True))
assert config['name'].startswith('editor-qualification-'),'QUALIFICATION_TARGET_REQUIRED'
identifier=str(uuid.uuid4());prefix='restored-mobile-resume-'+identifier
p=r/'evidence'/(prefix+'.json');output='evidence/'+prefix
candidate=pathlib.Path(os.environ['EDITOR_VERIFY_CANDIDATE_SCRIPT']).resolve();assert candidate.parent==t/'scripts'
run=json.loads((t/'evidence/source-spans-run.json').read_text());assert (run.get('job') or run)['generation_id']==generation,'RESTORED_RUN_GENERATION_MISMATCH'
report={'status':'RUNNING','semantic_acceptance':False,'model_calls':0,'generation_id':generation,'target':str(t),'failed_qualification_preserved':True,'frozen_bundle_unchanged':True}
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
report['frozen_verifier_sha256']=sha(t/'scripts/verify-review-ui.cjs');report['candidate_verifier_sha256']=sha(candidate)
def protected():
 q="SELECT json_build_object('records',(SELECT md5(COALESCE(string_agg(r.id::text||md5(row_to_json(r)::text),'' ORDER BY r.id),'')) FROM editor.records r),'reviews',(SELECT md5(COALESCE(string_agg(r.id::text||md5(row_to_json(r)::text),'' ORDER BY r.id),'')) FROM editor.reviews r),'active_jobs',(SELECT count(*) FROM editor.jobs WHERE status IN ('QUEUED','RUNNING')))"
 return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',q],text=True))
try:
 # Existing stopped qualification containers only; do not activate workers/models.
 ids={name:subprocess.check_output(['docker','compose','ps','-aq',name],text=True).strip() for name in ('postgres','qdrant','api','gateway')}
 assert all(ids.values()),'EXISTING_QUALIFICATION_CONTAINERS_REQUIRED'
 subprocess.run(['docker','start',ids['postgres'],ids['qdrant']],check=True,stdout=subprocess.DEVNULL)
 for _ in range(60):
  ready=subprocess.run(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc','SELECT 1'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
  if ready.returncode==0 and ready.stdout.strip()=='1':break
  time.sleep(2)
 else:raise RuntimeError('RESTORED_PG_NOT_READY')
 subprocess.run(['docker','start',ids['api'],ids['gateway']],check=True,stdout=subprocess.DEVNULL)
 for _ in range(60):
  try:
   req=urllib.request.Request(base+'/v1/me',headers={'Authorization':'Bearer '+(t/'secrets/api_token').read_text().strip()})
   with urllib.request.urlopen(req,timeout=5) as response:assert response.status==200
   break
  except Exception:time.sleep(2)
 else:raise RuntimeError('RESTORED_API_NOT_READY')
 report['before']=protected();assert report['before']['active_jobs']==0
 env={**os.environ,'EDITOR_VERIFY_BASE_URL':base,'EDITOR_VERIFY_RUN_FILE':'evidence/source-spans-run.json','EDITOR_VERIFY_OUTPUT_DIR':output,'EDITOR_VERIFY_CHARACTER_EVIDENCE':'1','EDITOR_VERIFY_REGIONAL_SOURCE':'1','EDITOR_VERIFY_OCR_VL_SELECTION':'1','EDITOR_VERIFY_FRAGMENTS':'1','EDITOR_VERIFY_CONTEXT_DIALOGUE':'1','EDITOR_VERIFY_SEMANTIC':'1'}
 with (r/'evidence'/(prefix+'.log')).open('x') as log:result=subprocess.run(['node',str(candidate)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
 report['returncode']=result.returncode;report['after']=protected();assert report['before']==report['after'],'PROTECTED_STATE_CHANGED'
 assert result.returncode==0,'RESTORED_MOBILE_FAILED'
 ui_path=t/output/'verification.json';ui=json.loads(ui_path.read_text())
 assert ui.get('results') and all(item['generation']==generation for item in ui['results']),'RESTORED_UI_GENERATION_MISMATCH'
 assert ui['api']==base,'RESTORED_UI_ENDPOINT_MISMATCH'
 report.update(status='PASS',ui_proof=str(ui_path))
except Exception as error:report.update(status='FAILED',error=str(error));raise
finally:
 with (r/'evidence'/(prefix+'-stop.log')).open('x') as log:stop=subprocess.run(['docker','compose','stop'],stdout=log,stderr=subprocess.STDOUT)
 report['target_stop_returncode']=stop.returncode
 if stop.returncode:report['status']='FAILED'
 p.write_text(json.dumps(report,indent=2));print(json.dumps(report))
