"""Server only. Explanation inputs: actual API vs independent raw Logo rows."""
import os, json, urllib.request, subprocess, hashlib
from pathlib import Path
from decimal import Decimal
from collections import defaultdict
from semantic_layer.profiler.connectors import connector_from_file
for line in Path('/etc/nanobase/semantic-bridge.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1);os.environ[k]=v.strip().strip('"').strip("'")
def api(path):
    return json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8795/api/v1/financial-audit/'+path,headers={'X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}),timeout=240))
ref=connector_from_file('/data/nanobaseai/bi/secrets/logo-mssql-connection.json')
def rows(sql):
    _,result,cut=ref.execute(sql,500000)
    assert not cut,'reference truncated'
    return result
D=lambda x:Decimal(str(x or 0)).quantize(Decimal('.0001'))
def ids(values):return ','.join(str(int(x)) for x in sorted(set(values))) or '0'
out=api('overview?year=2026');checks=[];samples={}
def check(name,ok):
    checks.append({'name':name,'status':'PASS' if ok else 'FAIL'})
    if len(checks)%10==0:print(json.dumps({'completed':len(checks),'pass':sum(c['status']=='PASS' for c in checks),'fail':sum(c['status']=='FAIL' for c in checks),'unverified':0}),flush=True)
cutoff=out['deepAudit']['asOf'];end=(__import__('datetime').date.fromisoformat(cutoff)+__import__('datetime').timedelta(days=1)).strftime('%Y%m%d')
for c in out['deepAudit']['checks']:
    if c['status']!='finding':continue
    data=api(f"runs/{out['runId']}/exceptions/{c['id']}?page=0")
    samples[c['id']]=data['items']
    check(c['id']+'-api-page',data['total']==c['affected'] and not data['truncated'] and len(data['items'])==min(50,c['affected']))
for key in ['invoice-unposted','invoice-account','bank-unposted']:
    sample=samples.get(key,[]);table='BNFLINE' if key.startswith('bank') else 'INVOICE';doc='TRANNO' if table=='BNFLINE' else 'FICHENO'
    source={r['LOGICALREF']:r for r in rows(f"SELECT LOGICALREF,{doc} AS DOC,ACCOUNTED"+(',ACCOUNTREF' if table=='INVOICE' else '')+f" FROM dbo.LG_411_01_{table} WHERE LOGICALREF IN ({ids(r['sourceRef'] for r in sample)})")}
    check(key+'-independent-reason',bool(sample) and all(str(source[r['sourceRef']]['DOC'])==r['documentNo'] and source[r['sourceRef']]['ACCOUNTED']==r['posted'] and (r['posted']==0 if key.endswith('unposted') else source[r['sourceRef']]['ACCOUNTREF']==r['accountRef'] and r['posted']==1 and not r['accountRef']) for r in sample))
vat=samples.get('invoice-vat-ledger',[]);bank=samples.get('bank-ledger-amount',[])
slips=ids([r['slipRef'] for r in vat+bank])
ledger=rows(f"SELECT L.ACCFICHEREF,L.ACCOUNTREF,L.DEBIT,L.CREDIT,A.CODE FROM dbo.LG_411_01_EMFLINE L LEFT JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF WHERE L.CANCELLED=0 AND L.DATE_>='20260101' AND L.DATE_<'{end}' AND L.ACCFICHEREF IN ({slips})")
gl=defaultdict(lambda:D(0));vgl=defaultdict(lambda:D(0))
for r in ledger:
    net=D(r['DEBIT'])-D(r['CREDIT']);gl[(r['ACCFICHEREF'],r['ACCOUNTREF'])]+=net
    if str(r['CODE'])[:3] in {'191','391'}:vgl[r['ACCFICHEREF']]+=net
iv=rows(f"SELECT ACCFICHEREF,TRCODE,TOTALVAT FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND ACCOUNTED=1 AND TRCODE IN (1,2,3,4,6,7,8,9) AND DATE_>='20260101' AND DATE_<'{end}' AND ACCFICHEREF IN ({ids(r['slipRef'] for r in vat)})")
vi=defaultdict(lambda:D(0))
for r in iv:vi[r['ACCFICHEREF']]+=D(r['TOTALVAT'])*(1 if r['TRCODE'] in [1,2,3,4] else -1)
for r in vat:
    actual=vgl.get(r['slipRef']);expected=vi[r['slipRef']];diff=expected-(actual or 0)
    check('vat-'+str(r['slipRef']),D(r['expected'])==expected and (r['actual'] is None)==(actual is None) and D(r['actual'])==D(actual) and D(r['difference'])==diff and abs(diff)>D('.01'))
# Read source bank movements and resolve direct links independently in Python.
bn=rows(f"SELECT ACCFICHEREF,EMFLINEREF,BNACCOUNTREF,SIGN,AMOUNT FROM dbo.LG_411_01_BNFLINE WHERE CANCELLED=0 AND ACCOUNTED=1 AND DATE_>='20260101' AND DATE_<'{end}'")
links={r['LOGICALREF']:r['ACCFICHEREF'] for r in rows('SELECT LOGICALREF,ACCFICHEREF FROM dbo.LG_411_01_EMFLINE WHERE LOGICALREF IN ('+ids(r['EMFLINEREF'] for r in bn if not r['ACCFICHEREF'])+')')}
bg=defaultdict(lambda:D(0))
for r in bn:
    if r['SIGN'] in [0,1]:bg[(r['ACCFICHEREF'] or links.get(r['EMFLINEREF']),r['BNACCOUNTREF'])]+=D(r['AMOUNT'])*(1 if r['SIGN']==0 else -1)
for r in bank:
    key=(r['slipRef'],r['accountRef']);actual=gl.get(key);expected=bg[key];diff=expected-(actual or 0)
    check('bank-'+str(key),D(r['expected'])==expected and (r['actual'] is None)==(actual is None) and D(r['actual'])==D(actual) and D(r['difference'])==diff and (actual is None or abs(diff)>D('.01')))
flagged={a['accountRef'] for a in out['accounts'] if a['unexpectedSign']}
for control in out['coverage']['items']:
    for c in control['components']:
        if c.get('id')=='balance-sign' and c['status']=='finding':flagged.update(c['accountRefs'])
accounts=[a for a in out['accounts'] if a['accountRef'] in flagged]
raw=rows(f"SELECT L.ACCOUNTREF,L.DEBIT,L.CREDIT FROM dbo.LG_411_01_EMFLINE L JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=L.ACCFICHEREF WHERE L.DATE_>='20260101' AND L.DATE_<'20270101' AND L.CANCELLED=0 AND F.CANCELLED=0 AND L.ACCOUNTREF IN ({ids(flagged)})")
acc=defaultdict(lambda:[D(0),D(0)])
for r in raw:acc[r['ACCOUNTREF']][0]+=D(r['DEBIT']);acc[r['ACCOUNTREF']][1]+=D(r['CREDIT'])
for a in accounts:
    debit,credit=acc[a['accountRef']];check('account-'+a['code'],D(a['debit'])==debit and D(a['credit'])==credit and D(a['balance'])==debit-credit and abs(debit-credit)>D('.01'))
payload={'runId':out['runId'],'samples':samples,'accounts':accounts,'coreChecks':out['checks'],'deepChecks':out['deepAudit']['checks']}
p=Path('/tmp/audit-findings-live.json');p.touch(mode=0o600);p.chmod(0o600);p.write_text(json.dumps(payload,ensure_ascii=False,default=str))
render=subprocess.run(['node','scripts/server/financial-audit-findings-acceptance.cjs'],check=False,capture_output=True,text=True)
check('actual-explanation-rendering',render.returncode==0)
report={'environment':'nanobase-direct actual API :8795; independent read-only Logo 2026 backup; no local/synthetic tests','runId':out['runId'],'checks':checks,'sampleRows':{k:len(v) for k,v in samples.items()},'accountRows':len(accounts),'render':json.loads(render.stdout) if render.stdout else {'error':render.stderr},'unverifiedRowScenarios':[c['id'] for c in out['deepAudit']['checks'] if not c['affected']],'sourceHashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('src/canvas/financial-audit').glob('*') if p.is_file()}}
p=Path('/tmp/financial-audit-findings-acceptance.json');p.touch(mode=0o600);p.chmod(0o600);p.write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'completed':len(checks),'pass':sum(c['status']=='PASS' for c in checks),'fail':sum(c['status']=='FAIL' for c in checks),'unverifiedRowScenarios':report['unverifiedRowScenarios'],'sampleRows':report['sampleRows'],'accountRows':len(accounts)},ensure_ascii=False),flush=True)
raise SystemExit(any(c['status']!='PASS' for c in checks))
