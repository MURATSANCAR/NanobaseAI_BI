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
    if len(checks)%10==0:
        print(json.dumps({'completed':len(checks),'pass':sum(c['status']=='PASS' for c in checks),'fail':sum(c['status']=='FAIL' for c in checks),'unverified':0}),flush=True)
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
    if ratio['note'] not in ratio_refs:
        continue
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
check('source-integrity',catalog['sha256']=='39ff5b294a1a62ade786228980251d14ab691820c6d16fb7fc677a1fe21039b3' and len(catalog['pages'])==241 and len(catalog['items'])==649 and catalog['completeControlCoverage'] is False)
# Extended coverage: independent row groups, not the application SQL or helpers.
_, flow_rows, cut = reference.execute("""SELECT ACCOUNTREF,F.TRCODE,L.TRCURR,
 COUNT(*) AS n,SUM(CAST(DEBIT AS decimal(28,4))) AS d,SUM(CAST(CREDIT AS decimal(28,4))) AS c
 FROM dbo.LG_411_01_EMFLINE L INNER JOIN dbo.LG_411_01_EMFICHE F ON F.LOGICALREF=L.ACCFICHEREF
 WHERE L.DATE_ >= '20260101' AND L.DATE_ < '20270101' AND L.CANCELLED=0 AND F.CANCELLED=0
 GROUP BY ACCOUNTREF,F.TRCODE,L.TRCURR""",10000)
check('flow-reference-not-truncated',not cut)
from collections import defaultdict
flow_ref=defaultdict(lambda:{'openingDebit':Decimal(0),'openingCredit':Decimal(0),'periodDebit':Decimal(0),'periodCredit':Decimal(0),'foreignRows':0})
for r in flow_rows:
    group='opening' if r['TRCODE']==1 else 'period'
    flow_ref[r['ACCOUNTREF']][group+'Debit']+=Decimal(str(r['d']))
    flow_ref[r['ACCOUNTREF']][group+'Credit']+=Decimal(str(r['c']))
    if r['TRCURR'] is not None and r['TRCURR'] not in [0,160]:flow_ref[r['ACCOUNTREF']]['foreignRows']+=r['n']
for field in ['openingDebit','openingCredit','periodDebit','periodCredit','foreignRows']:
    check('all-profile-'+field,all(abs(Decimal(str(p[field]))-flow_ref[p['accountRef']][field])<Decimal('.005') for p in out['profiles']))
def pf(prefix):
    return sum((v['periodDebit']-v['periodCredit'] for aid,v in flow_ref.items() if actual[aid]['code'].startswith(prefix)),Decimal(0))
sales=-pf('60')-pf('61'); cost=pf('62'); opex=pf('63'); finance=pf('660')+pf('661')
pretax=-sum((pf('6'+str(i)) for i in range(9)),Decimal(0)); net=pretax-pf('691')
opening_stock=sum((v['openingDebit']-v['openingCredit'] for aid,v in flow_ref.items() if actual[aid]['code'].startswith('153')),Decimal(0))
new_refs={16:(balance('25'),e),17:(balance('25'),u+e),22:(pf('621'),(opening_stock+balance('153'))/2),
23:(sales,balance('12')+balance('22')),24:(sales,d-k),25:(sales,balance('25')),26:(sales,balance('2')),27:(sales,e),28:(sales,a),
29:(net,e),30:(pretax,e),31:(pretax+finance,k+u+e),32:(net,a),33:(sales-cost-opex,a-balance('24')),
34:(-balance('54')-balance('57')-balance('58'),a),35:(sales-cost-opex,sales),36:(sales-cost,sales),37:(net,sales),38:(cost,sales),39:(opex,sales),40:(finance,sales),41:(pretax+finance,finance),42:(net+finance,finance)}
from datetime import date
elapsed=(date.fromisoformat(out['lastDate'][:10])-date(2026,1,1)).days+1
for ratio in out['ratios']:
    n=ratio['note']
    if n not in new_refs:continue
    num,den=new_refs[n]
    blocked=den<=0 or n in {22,29,32,37,42} or (n in {16,17,27,29,30,31,34} and abs(a-k-u-e)>Decimal('.01')) or (n in {29,30,31,32,33,35,36,37,38,39,40,41,42} and abs(pf('7'))>Decimal('.01'))
    check('extended-ratio-'+str(n),abs(Decimal(ratio['numerator'])-num)<Decimal('.005') and abs(Decimal(ratio['denominator'])-den)<Decimal('.005') and (ratio['value'] is None if blocked else abs(Decimal(ratio['value'])-num/den)<Decimal('1e-12')))
    if n in {22,23,24}:
        check('period-days-'+str(n),ratio['periodDays']==elapsed and (ratio.get('days') is None if blocked or num<=0 else abs(Decimal(ratio['days'])-elapsed*den/num)<Decimal('1e-12')))
check('all-41-analysis-notes',sorted(r['note'] for r in out['ratios'])==list(range(2,43)))
coverage=out['coverage']; controls={c['id']:c for c in coverage['items']}
check('every-source-occurrence-has-result',set(controls)==set(c['id'] for c in catalog['items']))
check('no-document-check-auto-pass',all(c['status']!='passed' for c in controls.values() if c['kind']!='analysis'))
check('distinct-duplicate-notes',all(k in controls for k in ['note-115-1','note-115-2','note-115-3','note-143-1','note-143-2','note-160-1','note-160-2']))
check('source-corrections-retained',all(controls['note-'+str(n)+'-1']['correction'] for n in [16,17,25,30,31,34,36,39,41,42,49,51,65,83,87,111,131,132,134,137,141,145,162,163,165,166]))
check('year-end-not-due',all(controls['note-'+str(n)+'-1']['status']=='not_due' for n in [53,98,147,148,165,166]))
check('loan-not-deposit',controls['note-131-1']['accountPrefixes']==['300'] and bool(controls['note-131-1']['correction']))
saved=api('runs/'+out['runId'])
check('snapshot-roundtrip',{k:v for k,v in saved.items() if k!='cached'}=={k:v for k,v in out.items() if k!='cached'})
# Independently derive same-voucher counterpart observations from per-main-account totals.
pair_defs=[('64','119','c',['654'],'d'),('73','129','c',['654'],'d'),('81','139','c',['654'],'d'),('82','150','c',['710','790'],'d'),('83','151','d',['711','721','731','799'],'c'),('84','151','c',['152'],'d'),('85','153','c',['621'],'d'),('86','157','c',['623'],'d'),('87','158','c',['654'],'d'),('93','181','d',['6'],'c'),('99','199','c',['654'],'d'),('104','229','c',['654'],'d'),('110','239','c',['654'],'d'),('111','241','c',['654'],'d'),('113','244','c',['654'],'d'),('114','247','c',['654'],'d'),('115','249','c',['654'],'d'),('127','281','d',['6'],'c'),('130','298','c',['654'],'d'),('162','501','c',['102'],'d')]
prefixes=sorted({x for _,p,_,others,_ in pair_defs for x in [p,*others]})
condition=' OR '.join("A.CODE LIKE '"+p+"%'" for p in prefixes)
_, voucher_rows, cut=reference.execute("""SELECT L.ACCFICHEREF AS v,LEFT(A.CODE,3) AS code,
 SUM(CAST(L.DEBIT AS decimal(28,4))) AS d,SUM(CAST(L.CREDIT AS decimal(28,4))) AS c
 FROM dbo.LG_411_01_EMFLINE L JOIN dbo.LG_411_EMUHACC A ON A.LOGICALREF=L.ACCOUNTREF
 WHERE L.CANCELLED=0 AND L.DATE_ >= '20260101' AND L.DATE_ < '20270101'
 AND L.ACCFICHEREF IN (SELECT LOGICALREF FROM dbo.LG_411_01_EMFICHE WHERE CANCELLED=0 AND TRCODE<>1)
 AND ("""+condition+") GROUP BY L.ACCFICHEREF,LEFT(A.CODE,3)",300000)
check('counterpart-reference-complete',not cut)
vouchers=defaultdict(list)
for r in voucher_rows:vouchers[r['v']].append(r)
for n,p,side,others,other_side in pair_defs:
    triggered=0; missing=0; amount=Decimal(0)
    for vr in vouchers.values():
        target=sum((Decimal(str(r[side])) for r in vr if r['code'].startswith(p)),Decimal(0))
        counterpart=sum((Decimal(str(r[other_side])) for r in vr if any(r['code'].startswith(o) for o in others)),Decimal(0))
        if target>Decimal('.01'):
            triggered+=1
            if counterpart<=Decimal('.01'):missing+=1;amount+=target
    result=out['pairChecks']['note-'+n+'-1']
    check('counterpart-note-'+n,result['triggered']==triggered and result['affected']==missing and abs(Decimal(result['amount'])-amount)<Decimal('.005'))
# Same-year VAT totals from an independent date-cutoff reference, not runtime SQL.
for m in out['vatMonths']:
    next_month=m['month']+1
    _, rr, cut=reference.execute(f"""SELECT LEFT(A.CODE,3) code,SUM(CAST(L.DEBIT AS decimal(28,4))) d,SUM(CAST(L.CREDIT AS decimal(28,4))) c
    FROM dbo.LG_411_EMUHACC A JOIN dbo.LG_411_01_EMFLINE L ON L.ACCOUNTREF=A.LOGICALREF
    WHERE L.CANCELLED=0 AND L.DATE_ >= '20260101' AND L.DATE_ < '2026{next_month:02}01'
    AND LEFT(A.CODE,3) IN ('190','191','391')
    AND L.ACCFICHEREF IN (SELECT LOGICALREF FROM dbo.LG_411_01_EMFICHE WHERE CANCELLED=0)
    GROUP BY LEFT(A.CODE,3)""",100)
    ref={r['code']:Decimal(str(r['d']))-Decimal(str(r['c'])) for r in rr}
    check('vat-month-'+str(m['month']),not cut and all(abs(Decimal(v)-ref.get(code,Decimal(0)))<Decimal('.005') for code,v in m['accounts'].items()))
report={'environment':'nanobase-direct → gerçek bridge HTTP :8795 → Logo SQL .155 / LOGO_DB','revision':out['revision'],'source':out['source'],'sourceLastDate':out['lastDate'],'checks':checks,'referenceSql':sql,'overview':out,'detail':detail,'nextPage':next_page}
Path('/tmp/financial-audit-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print(json.dumps({'completed':len(checks),'pass':sum(c['status']=='PASS' for c in checks),'fail':sum(c['status']=='FAIL' for c in checks),'unverified':0,'lines':out['lineCount'],'accounts':len(out['accounts']),'checks':out['checks'],'ratios':out['ratios']},ensure_ascii=False))
raise SystemExit(any(c['status']!='PASS' for c in checks))
