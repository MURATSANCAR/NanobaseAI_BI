#!/usr/bin/env python3
"""Recover actual immutable measurements into an empty isolated queue, no OCR."""
import argparse,hashlib,json,os,re,subprocess
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--canary-report',required=True,type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];os.chdir(root);canary=json.loads(a.canary_report.read_text())
assert canary['status']=='PASS' and re.fullmatch('[a-zA-Z0-9_]+',canary['database'])
row=next(r for r in canary['source_rows']['source_spans'] if r['data'].get('reread_generated_in_generation'))
evidence=canary['source_rows']['evidence'][0]
def snapshot():
 q="SELECT json_build_object('records',(SELECT md5(coalesce(string_agg(id::text||data::text,'' ORDER BY id),'')) FROM editor.records),'reviews',(SELECT count(*) FROM editor.reviews),'jobs',(SELECT count(*) FROM editor.jobs),'generations',(SELECT count(*) FROM editor.generations))"
 return json.loads(subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d',canary['database'],'-Atc',q],text=True))
before=snapshot()
runner=r'''
import hashlib,json,os,sys,tempfile
from pathlib import Path
p=json.load(sys.stdin);prov=p['provenance'];saved=Path(prov['artifact_path']);raw=saved.read_bytes();report=json.loads(raw);prior=report['request']
original_queue=Path('/data/reread-queue')
def snapshot():return {str(x):hashlib.sha256(x.read_bytes()).hexdigest() for folder in ('requests','results') for x in (original_queue/folder).glob('*.json')}
before=snapshot()
with tempfile.TemporaryDirectory(prefix='real-reread-recovery-') as temporary:
 os.environ['EDITOR_REREAD_QUEUE']=temporary
 from editor.reread_queue import QUEUE,capabilities,publish,submit,await_result,load_verified
 assert not list(QUEUE.iterdir());publish(QUEUE/'capabilities.json',capabilities())
 request=submit(prior['generation_id'],prior['source_sha256'],prior['pdf_page'],prior['render_sha256'],prior['regions'],languages=prior['languages'],deadline_seconds=prior['deadline_seconds'],expected_models=prior['models'],attempt_token=3)
 assert request==prior
 def check():assert saved.read_bytes()==raw
 measured,new_prov=await_result(request,check_active=check,queue_wait_seconds=5)
 assert measured==load_verified(prov,p['evidence']) and new_prov==prov
 attempts=list((QUEUE/'attempts').glob('*/*.json'));assert not attempts
 assert len(list((QUEUE/'requests').glob('*.json')))==len(list((QUEUE/'results').glob('*.json')))==1
 result={'status':'PASS','request_id':request['request_id'],'requested_attempt_token':3,'reused_attempt_token':request.get('attempt_token'),
  'same_artifact_sha256':hashlib.sha256(raw).hexdigest(),'reused_regions':len(measured),'new_ocr_attempts':len(attempts),'empty_queue_recovered':True,
  'existing_measurement_and_provenance_equal':True,'original_queue_unchanged':before==snapshot(),'semantic_acceptance':False,'component_only':True}
 assert result['original_queue_unchanged']
print(json.dumps(result))
'''
result=json.loads(subprocess.check_output(['docker','compose','exec','-T','reread-worker','python','-c',runner],input=json.dumps({'provenance':row['data']['reread_provenance'],'evidence':evidence}),text=True))
assert before==snapshot();result.update(database=canary['database'],generation_id=canary['generation_id'],db_unchanged=True,
 before_after=before,at=datetime.now(timezone.utc).isoformat(),verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
out=root/'evidence'/('reread-empty-queue-recovery-'+canary['generation_id']+'.json');out.write_text(json.dumps(result,indent=2));print(json.dumps(result|{'evidence':str(out)},indent=2))
