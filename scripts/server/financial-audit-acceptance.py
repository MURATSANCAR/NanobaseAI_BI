"""Independent reference against real Logo plus actual HTTP response; server only."""
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
from decimal import Decimal
from semantic_layer.profiler.connectors import connector_from_file

for line in Path('/etc/nanobase/semantic-bridge.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        key, value = line.split('=', 1)
        os.environ[key] = value.strip().strip('"').strip("'")
headers = {'X-Semantic-Caller': os.environ.get('SEMANTIC_CALLER_TOKEN', '')}
def api(path):
    return json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8795/api/v1/financial-audit/'+path, headers=headers), timeout=180))

out = api('overview?year=2026')
reference = connector_from_file('/data/nanobaseai/bi/secrets/logo-mssql-connection.json')
# Independent reference: first aggregate the ledger by account ID, then join the account
# plan. The implementation joins first. Verify every amount, account and row count.
sql = """SELECT A.LOGICALREF AS accountRef,A.CODE AS code,A.DEFINITION_ AS name,A.ACCTYPE AS accountType,
 Q.debit,Q.credit,Q.lineCount FROM dbo.LG_411_EMUHACC A INNER JOIN (
 SELECT ACCOUNTREF,SUM(CAST(DEBIT AS decimal(28,4))) debit,SUM(CAST(CREDIT AS decimal(28,4))) credit,COUNT(*) lineCount
 FROM dbo.LG_411_01_EMFLINE WHERE DATE_ >= '20260101' AND DATE_ < '20270101' AND CANCELLED=0
 AND ACCFICHEREF IN (SELECT LOGICALREF FROM dbo.LG_411_01_EMFICHE WHERE CANCELLED=0)
 GROUP BY ACCOUNTREF) Q ON Q.ACCOUNTREF=A.LOGICALREF ORDER BY A.CODE"""
cols, rows, truncated = reference.execute(sql, 10000)
actual = {x['accountRef']: x for x in out['accounts']}
checks = []
def check(name, ok, detail=None):
    checks.append({'name':name, 'status':'PASS' if ok else 'FAIL', 'detail':detail})
check('full-account-coverage', not truncated and not out['truncated'] and len(rows)==len(actual))
for field in ['code', 'name', 'lineCount', 'accountType', 'debit', 'credit']:
    valid = all(r['accountRef'] in actual and (abs(Decimal(str(r[field]))-Decimal(str(actual[r['accountRef']][field]))) < Decimal('.005') if field in ['debit','credit'] else r[field] == actual[r['accountRef']][field]) for r in rows)
    check('all-accounts-'+field, valid)
check('line-count',sum(r['lineCount'] for r in rows)==out['lineCount'],out['lineCount'])
check('all-balances',all(abs(Decimal(str(r['debit']))-Decimal(str(r['credit']))-Decimal(actual[r['accountRef']]['balance']))<Decimal('.005') for r in rows))
check('account-sign-flags',all(actual[r['accountRef']]['unexpectedSign']==(r['code'][:3] in {'100','101'} and Decimal(str(r['debit']))-Decimal(str(r['credit']))<Decimal('-.01')) for r in rows))
print(json.dumps({'completed':10,'pass':sum(c['status']=='PASS' for c in checks),'fail':sum(c['status']=='FAIL' for c in checks),'unverified':0}))
def balance(prefix):
    return sum((Decimal(str(r['debit']))-Decimal(str(r['credit'])) for r in rows if r['code'].startswith(prefix)), Decimal(0))
d,s,k,u,e=balance('1'),balance('15'),-balance('3'),-balance('4'),-balance('5')
a=d+balance('2'); cash=balance('10')+balance('11'); receivable=balance('12')+balance('13'); bank=-balance('300')-balance('303')-balance('400')
ratio_refs={2:(d,k),3:(d-s,k),4:(cash,k),5:(s,d),6:(s,a),7:(k-cash,s),8:(receivable,d),9:(receivable,a),10:(k+u,a),11:(e,a),12:(e,k+u),13:(k,k+u+e),14:(u,k+u+e),15:(u,u+e),18:(k,k+u),19:(bank,a),20:(bank,e),21:(d,a)}
for ratio in out['ratios']:
    numerator,denominator=ratio_refs[ratio['note']]
    check('ratio-'+str(ratio['note']),Decimal(ratio['numerator'])==numerator and Decimal(ratio['denominator'])==denominator and (ratio['value'] is None if denominator<=0 or (ratio['note'] in {11,12,13,14,15,20} and abs(a-k-u-e)>Decimal('.01')) else abs(Decimal(ratio['value'])-numerator/denominator)<Decimal('1e-12')))
    if len(checks)%10==0:
        print(json.dumps({'completed':len(checks),'pass':sum(c['status']=='PASS' for c in checks),'fail':sum(c['status']=='FAIL' for c in checks),'unverified':0}),flush=True)
_, fi, cut=reference.execute("SELECT ACCFICHEREF,SUM(CAST(DEBIT AS decimal(28,4))) AS debit,SUM(CAST(CREDIT AS decimal(28,4))) AS credit FROM dbo.LG_411_01_EMFLINE WHERE DATE_ >= '20260101' AND DATE_ < '20270101' AND CANCELLED=0 AND ACCFICHEREF IN (SELECT LOGICALREF FROM dbo.LG_411_01_EMFICHE WHERE CANCELLED=0) GROUP BY ACCFICHEREF",150000)
bad=[abs(Decimal(str(x['debit']))-Decimal(str(x['credit']))) for x in fi if abs(Decimal(str(x['debit']))-Decimal(str(x['credit'])))>Decimal('.01')]
slip_check=next(c for c in out['checks'] if c['id']=='slip-balance')
check('slip-imbalance-count',not cut and len(bad)==slip_check['affected'])
check('slip-imbalance-amount',abs(sum(bad,Decimal(0))-Decimal(slip_check['amount']))<Decimal('.005'))
print(json.dumps({'completed':len(checks),'pass':sum(c['status']=='PASS' for c in checks),'fail':sum(c['status']=='FAIL' for c in checks),'unverified':0}),flush=True)
account = next(x for x in out['accounts'] if x['lineCount']>50)
detail = api(f"lines?year=2026&account={account['accountRef']}&page=0")
next_page = api(f"lines?year=2026&account={account['accountRef']}&page=1")
check('detail-pagination', len(detail['items'])==50 and not ({x['lineRef'] for x in detail['items']} & {x['lineRef'] for x in next_page['items']}))
check('detail-total',detail['total']==account['lineCount'])
ids=','.join(str(x['lineRef']) for x in detail['items'])
_, ref_lines, cut=reference.execute(f"SELECT L.LOGICALREF AS lineRef,L.DEBIT AS debit,L.CREDIT AS credit,F.FICHENO AS slipNo FROM dbo.LG_411_01_EMFLINE L JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=L.ACCFICHEREF WHERE L.LOGICALREF IN ({ids})",100)
ref_map={r['lineRef']:r for r in ref_lines}
check('detail-values',not cut and all(x['slipNo']==ref_map[x['lineRef']]['slipNo'] and abs(Decimal(str(x['debit']))-Decimal(str(ref_map[x['lineRef']]['debit'])))<Decimal('.005') and abs(Decimal(str(x['credit']))-Decimal(str(ref_map[x['lineRef']]['credit'])))<Decimal('.005') for x in detail['items']))
for name, path, request_headers, expected in [
    ('unauthenticated-rejected', 'overview?year=2026', {}, 401),
    ('unauthenticated-source-rejected', 'catalog', {}, 401),
    ('unverified-period-rejected', 'overview?year=2025', headers, 422),
    ('invalid-account-rejected', 'lines?year=2026&account=-1', headers, 422),
]:
    try:
        response=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8795/api/v1/financial-audit/'+path,headers=request_headers),timeout=30)
        status=response.status
    except urllib.error.HTTPError as exc:
        status=exc.code
    check(name,status==expected,status)
catalog=api('catalog')
check('source-integrity',catalog['sha256']=='39ff5b294a1a62ade786228980251d14ab691820c6d16fb7fc677a1fe21039b3' and len(catalog['pages'])==241 and len(catalog['items'])==369 and catalog['completeControlCoverage'] is False)
report={'environment':'nanobase-direct → gerçek bridge HTTP :8795 → Logo SQL .155 / LOGO_DB','revision':out['revision'],'source':out['source'],'sourceLastDate':out['lastDate'],'checks':checks,'referenceSql':sql,'overview':out,'detail':detail,'nextPage':next_page}
Path('/tmp/financial-audit-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print(json.dumps({'completed':len(checks),'pass':sum(c['status']=='PASS' for c in checks),'fail':sum(c['status']=='FAIL' for c in checks),'unverified':0,'lines':out['lineCount'],'accounts':len(out['accounts']),'checks':out['checks'],'ratios':out['ratios']},ensure_ascii=False))
raise SystemExit(any(c['status']!='PASS' for c in checks))
