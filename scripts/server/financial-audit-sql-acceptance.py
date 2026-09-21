"""Server only: prove displayed SQL provenance against the independently accepted run."""
import json,os,hashlib,urllib.request
from pathlib import Path
from semantic_layer.profiler.connectors import connector_from_file
for line in Path('/etc/nanobase/semantic-bridge.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1);os.environ[k]=v.strip().strip('"').strip("'")
headers={'X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def api(path):return json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8795/api/v1/financial-audit/'+path,headers=headers),timeout=180))
accepted=json.loads(Path('/tmp/financial-audit-deep-acceptance.json').read_text())
assert all(c['status']=='PASS' for c in accepted['checks'])
out=api('runs/'+accepted['runId']);checks=[]
def check(name,ok):
    checks.append({'name':name,'status':'PASS' if ok else 'FAIL'})
    if len(checks)%10==0:print(json.dumps({'completed':len(checks),'pass':sum(x['status']=='PASS' for x in checks),'fail':sum(x['status']=='FAIL' for x in checks),'unverified':0}),flush=True)
check('current-backend',out['revision']==hashlib.sha256(Path('backend/semantic_bridge/financial_audit.py').read_bytes()).hexdigest())
for c in out['checks']:
    index=1 if c['id']=='slip-balance' else 2 if c['id']=='slip-link' else 0
    check('core-query-origin-'+c['id'],c.get('sql')==out['sql'][index] and bool(c.get('sqlPurpose')))
ref=connector_from_file('/data/nanobaseai/bi/secrets/logo-mssql-connection.json');seen={}
for c in out['deepAudit']['checks']:
    sql=c.get('sql');check('deep-query-origin-'+c['id'],bool(sql) and sql in out['deepAudit']['sql'])
    if sql not in seen:
        _,rows,cut=ref.execute(sql,10000);assert not cut;seen[sql]=rows[0]
    row=seen[sql];cols=c['sqlResultColumns']
    check('deep-query-result-column-'+c['id'],row[cols['tested']]==c['tested'] and (row[cols['affected']] or 0)==c['affected'])
for name in ['account-scope','balance-sign','voucher-counterpart','fx-profile']:
    observations=[c for item in out['coverage']['items'] for c in item['components'] if c.get('id')==name]
    check('rule-observation-query-'+name,bool(observations) and all(c.get('sql') in out['sql'] and c.get('sqlPurpose') for c in observations))
check('source-original-unchanged',api('catalog')==json.loads(Path('configs/financial-audit/source.json').read_text()))
# Actual presentation function runs on actual API catalog, on the server, not fixtures.
p=Path('/tmp/financial-audit-live-catalog.json');p.touch(mode=0o600);p.chmod(0o600);p.write_text(json.dumps(api('catalog'),ensure_ascii=False))
report={'environment':'nanobase-direct, real HTTP API and Logo DB','runId':out['runId'],'revision':out['revision'],'deepRevision':out['deepAudit']['revision'],'checks':checks,'independentReferenceAcceptance':'financial-audit-deep-acceptance.json','sqlQueryCount':len(seen)}
Path('/tmp/financial-audit-sql-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'completed':len(checks),'pass':sum(x['status']=='PASS' for x in checks),'fail':sum(x['status']=='FAIL' for x in checks),'unverified':0}),flush=True)
raise SystemExit(any(x['status']!='PASS' for x in checks))
