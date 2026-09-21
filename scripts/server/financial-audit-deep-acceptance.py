"""Server-only actual API vs independent raw Logo records. No application SQL reuse."""
import os, json, hashlib, urllib.request, urllib.error
from pathlib import Path
from decimal import Decimal
from collections import defaultdict
from datetime import timedelta, date
from semantic_layer.profiler.connectors import connector_from_file
for line in Path('/etc/nanobase/semantic-bridge.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k,v=line.split('=',1);os.environ[k]=v.strip().strip('"').strip("'")
base='http://127.0.0.1:8795/api/v1/financial-audit/'
headers={'X-Semantic-Caller':os.environ['SEMANTIC_CALLER_TOKEN']}
def http(path,auth=True):
    return urllib.request.urlopen(urllib.request.Request(base+path,headers=headers if auth else {}),timeout=240)
def api(path):return json.load(http(path))
out=api('overview?year=2026');deep=out['deepAudit'];checks=[]
assert deep['revision']==hashlib.sha256(Path('backend/semantic_bridge/financial_audit_deep.py').read_bytes()).hexdigest(),'stale deep deployment'
ref=connector_from_file('/data/nanobaseai/bi/secrets/logo-mssql-connection.json')
D=lambda x:Decimal(str(x or 0))
def check(name,ok,detail=None):
    checks.append({'name':name,'status':'PASS' if ok else 'FAIL','detail':detail})
    if len(checks)%10==0:print(json.dumps({'completed':len(checks),'pass':sum(x['status']=='PASS' for x in checks),'fail':sum(x['status']=='FAIL' for x in checks),'unverified':0}),flush=True)
def rows(sql,limit=500000):
    _,r,cut=ref.execute(sql,limit)
    assert not cut,'reference truncated'
    return r
end=(date.fromisoformat(deep['asOf'])+timedelta(days=1)).strftime('%Y%m%d')
period=f"DATE_>='20260101' AND DATE_<'{end}' AND CANCELLED=0"
check('deep-all-sources-read',not deep['errors'],deep['errors'])
# Independent raw reads, Python joins and grouping. No application functions/SQL.
f={r['LOGICALREF']:r for r in rows('SELECT LOGICALREF,CANCELLED,DATE_,FICHENO FROM dbo.LG_411_01_EMFICHE')}
a={r['LOGICALREF']:r for r in rows('SELECT LOGICALREF,CODE FROM dbo.LG_411_EMUHACC')}
ledger=rows('SELECT LOGICALREF,ACCFICHEREF,ACCOUNTREF,DEBIT,CREDIT,DATE_,CANCELLED FROM dbo.LG_411_01_EMFLINE')
lmap={r['LOGICALREF']:r for r in ledger};gl=defaultdict(lambda:[D(0),0]);vatgl=defaultdict(lambda:D(0));cashday=defaultdict(lambda:D(0))
for r in ledger:
    if r['CANCELLED'] or not ('2026-01-01'<=str(r['DATE_'])[:10]<=deep['asOf']):continue
    key=(r['ACCFICHEREF'],r['ACCOUNTREF']);net=D(r['DEBIT']).quantize(D('.0001'))-D(r['CREDIT']).quantize(D('.0001'))
    gl[key][0]+=net;gl[key][1]+=1
    code=a.get(r['ACCOUNTREF'],{}).get('CODE','')
    if code[:3] in {'191','391'}:vatgl[r['ACCFICHEREF']]+=net
    if code.startswith('100') and r['ACCFICHEREF'] in f and f[r['ACCFICHEREF']]['CANCELLED']==0:cashday[(r['ACCOUNTREF'],str(r['DATE_'])[:10])]+=net
inv=rows('SELECT LOGICALREF,FICHENO,DATE_,CLIENTREF,TRCODE,ACCOUNTREF,ACCFICHEREF,ACCOUNTED,NETTOTAL,TOTALVAT FROM dbo.LG_411_01_INVOICE WHERE '+period)
bank=rows('SELECT LOGICALREF,DATE_,TRANNO,ACCOUNTED,SIGN,MODULENR,BNACCREF,BNACCOUNTREF,EMFLINEREF,ACCFICHEREF,AMOUNT,TRCURR FROM dbo.LG_411_01_BNFLINE WHERE '+period)
# Each expected record carries every displayed column, not just a row count.
expected={k:[] for k in ['invoice-unposted','invoice-broken-link','invoice-date','invoice-account','invoice-ledger-amount','invoice-vat-ledger','invoice-vat-lines','bank-unposted','bank-broken-link','bank-account','bank-ledger-amount','cash-negative-day']}
ig=defaultdict(list);vg=defaultdict(list);types=defaultdict(lambda:[0,0])
for r in inv:
    F=f.get(r['ACCFICHEREF']);types[r['TRCODE']][0]+=1;types[r['TRCODE']][1]+=r['ACCOUNTED']==0
    record=dict(sourceRef=r['LOGICALREF'],documentNo=r['FICHENO'],date=r['DATE_'],clientRef=r['CLIENTREF'],transactionType=r['TRCODE'],accountRef=r['ACCOUNTREF'],slipRef=r['ACCFICHEREF'],posted=r['ACCOUNTED'],amount=D(r['NETTOTAL']).quantize(D('.0001')),vat=D(r['TOTALVAT']).quantize(D('.0001')),foundSlip=F['LOGICALREF'] if F else None,cancelledSlip=F['CANCELLED'] if F else None,ledgerDate=F['DATE_'] if F else None)
    if r['ACCOUNTED']==0:expected['invoice-unposted'].append(record)
    if r['ACCOUNTED']==1 and (not F or F['CANCELLED']):expected['invoice-broken-link'].append(record)
    if F and r['DATE_']!=F['DATE_']:expected['invoice-date'].append(record)
    if r['ACCOUNTED']==1 and not r['ACCOUNTREF']:expected['invoice-account'].append(record)
    if r['ACCOUNTED']==1 and r['TRCODE'] in [1,2,3,4,6,7,8,9] and r['ACCFICHEREF']>0 and F and not F['CANCELLED']:
        vg[r['ACCFICHEREF']].append(r)
        if r['ACCOUNTREF']>0:ig[(r['ACCFICHEREF'],r['ACCOUNTREF'])].append(r)
for (fid,aid),group in ig.items():
    exp=sum((D(r['NETTOTAL']).quantize(D('.0001'))*(-1 if r['TRCODE'] in [1,2,3,4] else 1) for r in group),D(0));act=gl.get((fid,aid));diff=exp-(act[0] if act else 0)
    if abs(diff)>D('.01') or act is None:expected['invoice-ledger-amount'].append(dict(slipRef=fid,accountRef=aid,accountCode=a.get(aid,{}).get('CODE'),invoiceCount=len(group),expected=exp,actual=act[0] if act else None,difference=diff,lineCount=act[1] if act else None,firstDate=min(r['DATE_'] for r in group),lastDate=max(r['DATE_'] for r in group),slipNo=f[fid]['FICHENO'],ledgerDate=f[fid]['DATE_']))
for fid,group in vg.items():
    exp=sum((D(r['TOTALVAT']).quantize(D('.0001'))*(1 if r['TRCODE'] in [1,2,3,4] else -1) for r in group),D(0));act=vatgl.get(fid);diff=exp-(act or 0)
    if abs(diff)>D('.01'):expected['invoice-vat-ledger'].append(dict(slipRef=fid,invoiceCount=len(group),expected=exp,actual=act,difference=diff,documentNo=f[fid]['FICHENO'],date=f[fid]['DATE_']))
# Header VAT independent line groups; compare full returned table values.
stockvat=rows('SELECT INVOICEREF,SUM(CAST(VATAMNT AS decimal(28,4))) AS total,COUNT(*) AS n FROM dbo.LG_411_01_STLINE WHERE CANCELLED=0 AND INVOICEREF>0 GROUP BY INVOICEREF')
sv={r['INVOICEREF']:r for r in stockvat}
for r in inv:
    v=sv.get(r['LOGICALREF']);exp=D(r['TOTALVAT']).quantize(D('.0001'));diff=exp-(D(v['total']) if v else 0)
    if abs(diff)>D('.01') or not v:expected['invoice-vat-lines'].append(dict(sourceRef=r['LOGICALREF'],documentNo=r['FICHENO'],date=r['DATE_'],slipRef=r['ACCFICHEREF'],expected=exp,actual=D(v['total']) if v else None,lineCount=v['n'] if v else None,difference=diff))
bg=defaultdict(list);direct=0
for r in bank:
    E=lmap.get(r['EMFLINEREF']);fid=r['ACCFICHEREF'] or (E['ACCFICHEREF'] if E else None);F=f.get(fid);A=a.get(r['BNACCOUNTREF'])
    record=dict(sourceRef=r['LOGICALREF'],date=r['DATE_'],documentNo=r['TRANNO'],posted=r['ACCOUNTED'],direction=r['SIGN'],sourceModule=r['MODULENR'],bankAccountRef=r['BNACCREF'],accountRef=r['BNACCOUNTREF'],directLineRef=r['EMFLINEREF'],slipRef=fid,foundSlip=F['LOGICALREF'] if F else None,cancelledSlip=F['CANCELLED'] if F else None,foundLine=E['LOGICALREF'] if E else None,cancelledLine=E['CANCELLED'] if E else None,foundAccount=A['LOGICALREF'] if A else None,accountCode=A['CODE'] if A else None,amount=D(r['AMOUNT']).quantize(D('.0001')),currency=r['TRCURR'],ledgerDate=F['DATE_'] if F else None)
    if r['ACCOUNTED']==0:expected['bank-unposted'].append(record)
    if r['ACCOUNTED']==1 and (not F or F['CANCELLED'] or (r['EMFLINEREF']>0 and (not E or E['CANCELLED']))):expected['bank-broken-link'].append(record)
    if r['ACCOUNTED']==1 and not A:expected['bank-account'].append(record)
    if r['ACCOUNTED']==1 and F and not F['CANCELLED'] and A and r['SIGN'] in [0,1]:bg[(fid,r['BNACCOUNTREF'])].append(r)
    if r['ACCOUNTED']==1 and not r['ACCFICHEREF'] and E and F and not F['CANCELLED']:direct+=1
for (fid,aid),group in bg.items():
    exp=sum((D(r['AMOUNT']).quantize(D('.0001'))*(1 if r['SIGN']==0 else -1) for r in group),D(0));act=gl.get((fid,aid));diff=exp-(act[0] if act else 0)
    if abs(diff)>D('.01') or act is None:expected['bank-ledger-amount'].append(dict(slipRef=fid,accountRef=aid,accountCode=a[aid]['CODE'],sourceCount=len(group),expected=exp,actual=act[0] if act else None,difference=diff,date=f[fid]['DATE_'],documentNo=f[fid]['FICHENO']))
cashrunning=defaultdict(lambda:D(0))
for (aid,dt),net in sorted(cashday.items()):
    cashrunning[aid]+=net
    if cashrunning[aid]<D('-.01'):expected['cash-negative-day'].append(dict(accountRef=aid,accountCode=a[aid]['CODE'],date=dt,balance=cashrunning[aid]))
def same(x,y):
    if x is None or y is None:return x is None and y is None
    if isinstance(y,(int,float,Decimal)):return abs(D(x)-D(y))<D('.0001')
    return str(x).replace('T',' ')==str(y).replace('T',' ')
tested={**{k:len(inv) for k in ['invoice-unposted','invoice-broken-link','invoice-date','invoice-account','invoice-vat-lines']},**{k:len(bank) for k in ['bank-unposted','bank-broken-link','bank-account']},'invoice-ledger-amount':len(ig),'invoice-vat-ledger':len(vg),'bank-ledger-amount':len(bg),'cash-negative-day':len(cashday)}
actual={c['id']:c for c in deep['checks']}
for key,want in expected.items():
    got=actual[key];check(key+'-full-count',got['affected']==len(want) and got['tested']==tested[key],{'actual':got['affected'],'reference':len(want),'tested':tested[key]})
    check(key+'-status',got['status']==('unverified' if not tested[key] else 'finding' if want else 'passed'))
    sort=lambda r: (r['accountRef'],str(r['date'])) if key=='cash-negative-day' else (r['slipRef'],r['accountRef']) if key in ['invoice-ledger-amount','bank-ledger-amount'] else (r['slipRef'],) if key=='invoice-vat-ledger' else (str(r['date']),r['sourceRef'])
    want.sort(key=sort)
    pages=list(dict.fromkeys([0,1,len(want)//50]))
    for page in pages:
        got=api(f"runs/{out['runId']}/exceptions/{key}?page={page}");slice_=want[page*50:(page+1)*50]
        check(key+f'-page-{page}-full-values',got['total']==len(want) and got['truncated'] is False and got['separateRead'] and len(got['items'])==len(slice_) and all(set(x)-{'totalRows'}==set(y) and all(same(x[k],v) for k,v in y.items()) for x,y in zip(got['items'],slice_)))
check('bank-direct-links-preserved',direct==98,{'directLinks':direct})
check('invoice-type-full-profile',len(types)==len(deep['datasets']['invoiceTypes']) and all([r['rows'],r['unposted']]==types[r['type']] for r in deep['datasets']['invoiceTypes']))
# Independent source-presence references, including periods and currency separation.
tax=rows('SELECT YEAR_,MONTH_,TYP FROM dbo.LG_411_TAXDECLHDR');taxg=defaultdict(int)
for r in tax:taxg[(r['YEAR_'],r['MONTH_'],r['TYP'])]+=1
check('tax-full-period-profile',{(r['year'],r['month'],r['type']):r['rows'] for r in deep['datasets']['taxPeriods']}==taxg)
check('missing-current-declaration-explained',next(s for s in deep['sources'] if s['id']=='tax')['status']=='missing' and sum(r['YEAR_']==2026 for r in tax)==0)
loan=rows("SELECT P.TRANSTYPE,P.DUEDATE,P.TOTAL,P.INTTOTAL,P.BNFCHREF,C.LOGICALREF,C.TRCURR FROM dbo.LG_411_BNCREPAYTR P LEFT JOIN dbo.LG_411_BNCREDITCARD C ON P.CREDITREF=C.LOGICALREF WHERE P.DUEDATE>='20260101' AND P.DUEDATE<'20270101'");lg=defaultdict(list)
for r in loan:lg[(r['TRANSTYPE'],r['TRCURR'])].append(r)
check('loan-currency-and-type-coverage',set(lg)=={(r['type'],r['currency']) for r in deep['datasets']['loanSchedule']})
for r in deep['datasets']['loanSchedule']:
    group=lg[(r['type'],r['currency'])]
    want=dict(rows=len(group),bankLinked=sum(x['BNFCHREF']>0 for x in group),missingCredit=sum(x['LOGICALREF'] is None for x in group),firstDate=min(x['DUEDATE'] for x in group),lastDate=max(x['DUEDATE'] for x in group),principal=sum((D(x['TOTAL']).quantize(D('.0001')) for x in group),D(0)),interest=sum((D(x['INTTOTAL']).quantize(D('.0001')) for x in group),D(0)))
    check('loan-profile-'+str(r['type'])+'-'+str(r['currency']),all(same(r[k],v) for k,v in want.items()))
stocks=rows("SELECT TRCODE,DATE_ FROM dbo.LG_411_01_STFICHE WHERE CANCELLED=0 AND DATE_>='20260101' AND DATE_<'20270101'");sg=defaultdict(list)
for r in stocks:sg[r['TRCODE']].append(r)
check('stock-full-profile',len(sg)==len(deep['datasets']['stockSlips']) and all(r['rows']==len(sg[r['type']]) and r['afterCutoff']==sum(str(x['DATE_'])[:10]>deep['asOf'] for x in sg[r['type']]) and same(r['firstDate'],min(x['DATE_'] for x in sg[r['type']])) and same(r['lastDate'],max(x['DATE_'] for x in sg[r['type']])) for r in deep['datasets']['stockSlips']))
check('future-stock-not-hidden',sum(r['afterCutoff'] for r in deep['datasets']['stockSlips'])>0)
ebooks=rows('SELECT PERYEAR,PERMONTH,TYP,BOOKSTATUS,REPORTSTARTDATE,REPORTENDDATE,JOURNALCOUNT FROM dbo.LG_411_EBOOKINFO WHERE PERYEAR=2026 ORDER BY PERMONTH,TYP')
mapping=dict(year='PERYEAR',month='PERMONTH',type='TYP',state='BOOKSTATUS',firstDate='REPORTSTARTDATE',lastDate='REPORTENDDATE',journalCount='JOURNALCOUNT')
check('ebook-full-profile',len(ebooks)==len(deep['datasets']['ebookPeriods']) and all(all(same(x[k],y[v]) for k,v in mapping.items()) for x,y in zip(deep['datasets']['ebookPeriods'],ebooks)))
# Latest cheque state derived in Python; raw codes are deliberately not legal statuses.
cards={r['LOGICALREF']:r for r in rows('SELECT LOGICALREF,DOC,TRCURR,DUEDATE,AMOUNT FROM dbo.LG_411_01_CSCARD WHERE CANCELLED=0')}
trans=rows(f"SELECT LOGICALREF,CSREF,STATUS,DATE_ FROM dbo.LG_411_01_CSTRANS WHERE CANCELLED=0 AND DATE_<'{end}'")
latest={}
for r in sorted(trans,key=lambda r:(str(r['DATE_']),r['LOGICALREF'])):latest[r['CSREF']]=r
cg=defaultdict(lambda:dict(rows=0,dueByCutoff=0,amount=D(0)))
for rid,r in cards.items():
    if rid not in latest:continue
    g=cg[(r['DOC'],latest[rid]['STATUS'],r['TRCURR'])];g['rows']+=1;g['dueByCutoff']+=r['DUEDATE'] is not None and str(r['DUEDATE'])[:10]<=deep['asOf'];g['amount']+=D(r['AMOUNT']).quantize(D('.0001'))
check('cheques-full-profile',len(cg)==len(deep['datasets']['chequeStates']) and all(all(same(r[k],v) for k,v in cg[(r['documentType'],r['state'],r['currency'])].items()) for r in deep['datasets']['chequeStates']))
exports=rows('SELECT INVOICEREF,CUSTDOCNO,CUSTDOCDATE FROM dbo.LG_411_01_INVEXIMINFO')
invrefs={r['LOGICALREF'] for r in inv};exports=[r for r in exports if r['INVOICEREF'] in invrefs]
ex=deep['datasets']['exportDocuments'][0]
check('exports-full-profile',ex['rows']==len(exports) and (ex['missingCustomsNumber'] or 0)==sum(not (r['CUSTDOCNO'] or '').strip() for r in exports) and (ex['missingCustomsDate'] or 0)==sum(r['CUSTDOCDATE'] is None or str(r['CUSTDOCDATE'])[:10]<'1901-01-01' for r in exports))
# Read only length and hex prefix, never contents/names. Decode signature independently.
attachments=rows('SELECT INFOTYP,DOCTYP,DATALENGTH(LDATA) AS bytes,CONVERT(varchar(32),SUBSTRING(LDATA,1,16),2) AS prefix FROM dbo.LG_411_01_PERDOC')
ag=defaultdict(lambda:dict(rows=0,withPayload=0,addressNotes=0,pdfSignatures=0,xmlSignatures=0))
for r in attachments:
    g=ag[(r['INFOTYP'],r['DOCTYP'])];g['rows']+=1;g['withPayload']+=(r['bytes'] or 0)>0
    b=bytes.fromhex(r['prefix'] or '');g['addressNotes']+=b[1:15]==b'Fatura Adresi:';g['pdfSignatures']+=b.startswith(b'%PDF');g['xmlSignatures']+=b.startswith(b'<?xml')
check('attachments-full-signature-profile',len(ag)==len(deep['datasets']['attachments']) and all(all(r[k]==v for k,v in ag[(r['type'],r['documentType'])].items()) for r in deep['datasets']['attachments']))
check('all-source-gaps-explained',len(deep['sources'])==9 and all(s['missing'] and s['why'] and s['nextStep'] and s['status'] in ['partial','missing'] for s in deep['sources']))
controls={c['id']:c for c in out['coverage']['items']}
pnl_codes=['600','601','602','640','641','642','643','644','645','646','647','649','671','649','610','611','612','620','621','622','623','630','631','632','653',None,'655','656','657','659','660','661','680','681','689']
for i,code in enumerate(pnl_codes,1):
    page=236 if i<=18 else 237 if i<=32 else 238
    c=controls[f'item-{page}-{i}-1']
    check('pnl-checklist-account-'+str(i),c['accountPrefixes']==([code] if code else []) and set(c['accountRefs'])=={a['accountRef'] for a in out['accounts'] if code and a['code'].startswith(code)})
check('ambiguous-source-caption-not-guessed',controls['item-237-26-1']['status']=='unverified' and not controls['item-237-26-1']['accountRefs'])
# Export transport is real: exact immutable archive bytes, complete JSON and integrity header.
with http(f"runs/{out['runId']}/export") as response:
    blob=response.read();exportheaders=dict(response.headers)
archive=Path('/data/nanobaseai/bi/var/financial-audit/workpapers')/(out['runId']+'.json')
check('export-exact-archive-bytes',blob==archive.read_bytes())
check('export-integrity-header',hashlib.sha256(blob).hexdigest()==exportheaders.get('x-content-sha256',exportheaders.get('X-Content-SHA256')))
check('export-complete-json',json.loads(blob)==api('runs/'+out['runId']))
check('export-attachment', 'attachment;' in str(exportheaders.get('content-disposition',exportheaders.get('Content-Disposition',''))))
for path,expected_status in [(f"runs/{out['runId']}/export",401),(f"runs/{out['runId']}/exceptions/invoice-unposted",401)]:
    try:http(path,False);status=200
    except urllib.error.HTTPError as ex:status=ex.code
    check('private-'+path,status==expected_status)
report={'environment':'nanobase-direct → actual HTTP :8795 → real Logo .155/LOGO_DB','runId':out['runId'],'revision':out['revision'],'deepRevision':deep['revision'],'checks':checks,'overview':out,'exportSha256':hashlib.sha256(blob).hexdigest(),'exceptionCoverage':'Complete result counts; all columns and values in first, second and final/empty pages for every check. References from separate raw DB reads.'}
p=Path('/tmp/financial-audit-deep-acceptance.json');p.touch(mode=0o600);p.chmod(0o600);p.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str))
print(json.dumps({'completed':len(checks),'pass':sum(x['status']=='PASS' for x in checks),'fail':sum(x['status']=='FAIL' for x in checks),'unverified':0,'counts':{k:len(v) for k,v in expected.items()}},ensure_ascii=False),flush=True)
raise SystemExit(any(x['status']!='PASS' for x in checks))
