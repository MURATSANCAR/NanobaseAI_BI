"""Connected test-server acceptance for Logo reports; no product/compiler imports.

Independent references read source rows and calculate in this runner. No API SQL
is re-executed. Source-relative boundaries are separate from numeric answer PASS.
Existing timasai session only; no Logo/CRM writes. Never run on a workstation.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

# Acceptance transport helpers only. These do not import product code.
import composable_live as transport

START, END, AS_OF = "2026-09-01", "2026-10-01", "2026-09-30"
D = lambda value: Decimal(str(value or 0))
QUANTITY_COLUMNS = frozenset({"onhand", "source_quantity", "movement_quantity", "daily_change",
                             "ordered_quantity", "shipped_quantity", "remaining_quantity",
                             "remaining_base_quantity", "purchase_quantity"})


def quote(value):return "N'"+str(value).replace("'","''")+"'"


class Reader:
    def __init__(self, conn):self.conn=conn;self.evidence=[]
    def read(self,sql):
        rows=transport.query(self.conn,sql)
        self.evidence.append({"sql":sql,"rows":rows})
        return rows


def seed(reader):
    # Source record2 is a labelled acceptance anchor from bounded field research,
    # never a production rule. Its current code is read rather than hard-coded.
    book=reader.read("SELECT CODE FROM dbo.LG_411_ITEMS WHERE LOGICALREF=2")
    if len(book)!=1:raise RuntimeError("Observed stock reference2 is no longer uniquely available")
    payer=reader.read("SELECT TOP(1) C.CODE FROM dbo.LG_411_01_CLFLINE L JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE C.CODE LIKE '120%' AND L.CANCELLED=0 AND L.SIGN=1 AND L.TRCODE IN (1,20,61,62,70) AND L.DATE_>='20260901' AND L.DATE_<'20261001' ORDER BY L.LOGICALREF DESC")
    order=reader.read("SELECT TOP(1) I.CODE FROM dbo.LG_411_01_ORFLINE O JOIN dbo.LG_411_01_ORFICHE H ON H.LOGICALREF=O.ORDFICHEREF JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=O.STOCKREF WHERE O.TRCODE=1 AND O.LINETYPE=0 AND O.CANCELLED=0 AND H.CANCELLED=0 AND O.CLOSED=0 AND O.AMOUNT>O.SHIPPEDAMOUNT AND O.DATE_>='20260101' AND O.DATE_<'20261001' ORDER BY O.LOGICALREF DESC")
    purchase=reader.read("SELECT TOP(1) I.CODE FROM dbo.LG_411_01_STLINE S JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=S.STOCKREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.TRCODE=1 AND S.INVOICEREF<>0 AND S.DATE_>='20260901' AND S.DATE_<'20261001' ORDER BY S.LOGICALREF DESC")
    return {"book":str(book[0]["CODE"]).strip(),"payer":payer[0]["CODE"] if payer else None,
            "order_book":str(order[0]["CODE"]).strip() if order else None,
            "purchase_book":str(purchase[0]["CODE"]).strip() if purchase else None}


def cases(anchors):
    book=anchors["book"];payer=anchors["payer"];order=anchors["order_book"];purchase=anchors["purchase_book"]
    common=["stock_ref","book_code","book_name","warehouse_no"]
    stock_fields=common+["onhand","source_quantity","movement_quantity","reconciliation"]
    out=[
        dict(id="LR001",mode="stock",question=f"Logo'da stok kodu {book} olan kitabın 30 Eylül 2026 sonu itibarıyla bütün depolardaki stok miktarlarını göster. Kaynak stokla hareket toplamı uzlaşmıyorsa kesin miktar verme.",book=book,as_of=AS_OF,columns=stock_fields,keys=["stock_ref","warehouse_no"]),
        dict(id="LR002",mode="stock",question=f"Logo'da stok kodu {book} olan kitabın 16 Ocak 2026 sonu stok miktarını depo depo göster.",book=book,as_of="2026-01-16",columns=stock_fields,keys=["stock_ref","warehouse_no"]),
        dict(id="LR003",mode="stock_history",question=f"Logo'da stok kodu {book} olan kitabın 1 Eylül 2026 dahil, 8 Eylül 2026 hariç hareket olan günlerdeki stok değişimini ve gün sonu stoğunu depo bazında ver.",book=book,start=START,end="2026-09-08",as_of="2026-09-07",columns=common+["day","daily_change","onhand","source_quantity","movement_quantity","reconciliation"],keys=["stock_ref","warehouse_no","day"]),
        dict(id="LR004",mode="open_orders",question=f"Logo'da stok kodu {order} olan kitabın 2026 başından 30 Eylül 2026 sonuna kadar verilmiş, bugün açık duran satış sipariş satırlarını göster. Sipariş, sevk ve kalan adet; satır birimi, vade, gecikme ve oransal kalan net tutar da olsun. Stok tahsisi yapma.",book=order,start="2026-01-01",end=END,as_of=AS_OF,columns=["source_period","order_line_ref","order_number","order_date","book_code","book_name","customer_code","customer_name","warehouse_no","unit_ref","ordered_quantity","shipped_quantity","remaining_quantity","remaining_base_quantity","remaining_net_amount_proportional","due_date","overdue_days"],keys=["source_period","order_line_ref"],requires="order_book"),
        dict(id="LR005",mode="customer_balances",question=f"Logo'da cari kodu {payer} için Eylül 2026 başlangıç bakiyesi, ay içi borç ve alacak hareketi toplamları ve ay sonu bakiyesini göster. Fatura yaşlandırması istemiyorum.",customer=payer,start=START,end=END,columns=["customer_code","customer_name","tax_number","opening_balance","period_debits","period_credits","closing_balance","unverified_sign_rows"],keys=["customer_code","customer_name","tax_number"],requires="payer"),
        dict(id="LR006",mode="payment_movements",question=f"Logo'da cari kodu {payer} için Eylül 2026 müşteri ödeme hareketlerini nakit, banka, çek, senet ve kart türlerine ayır; her türün hareket sayısı ve tutarı olsun. Çek ve senet teslimini nakit sayma.",customer=payer,start=START,end=END,columns=["customer_code","customer_name","payment_code","payment_type","movement_count","payment_amount"],keys=["customer_code","customer_name","payment_code"],requires="payer"),
        dict(id="LR007",mode="currencies",question="Logo'da Eylül 2026 satış ve iade faturalarını işlem para birimine göre ayır. Fatura sayısı, iade düşülmüş yerel fatura genel toplamı ve özgün işlem para birimi genel toplamı olsun; farklı dövizleri toplama, tanımlanamayan para birimini tahmin etme.",start=START,end=END,columns=["currency_id","currency_code","invoice_count","local_invoice_net","original_invoice_net"],keys=["currency_id","currency_code"]),
        dict(id="LR008",mode="purchase_prices",question=f"Logo'da stok kodu {purchase} olan kitabın Eylül 2026 faturalı alışlarını tedarikçi, satır birimi, işlem para birimi ve ay bazında göster. Alış miktarı, KDV hariç net alış tutarı ve ağırlıklı birim alış fiyatı olsun; bunu satılan mal maliyeti sayma.",book=purchase,start=START,end=END,columns=["book_code","book_name","supplier_code","supplier_name","month","unit_source","unit_ref","unit_factor_1","unit_factor_2","transaction_currency_id","purchase_quantity","purchase_net_amount","weighted_unit_purchase_price"],keys=["book_code","book_name","supplier_code","supplier_name","month","unit_source","unit_ref","unit_factor_1","unit_factor_2","transaction_currency_id"],requires="purchase_book"),
        dict(id="LR009",mode="aging",question="Logo'da 30 Eylül 2026 itibarıyla kesin açık alacak yaşlandırmasını gerçek fatura ödeme kapama kayıtlarıyla çıkar; FIFO veya yalnız toplam borçtan tahmin etme.",as_of=AS_OF,boundary="PAYMENT_CLOSURE_UNVERIFIED"),
        dict(id="LR010",mode="profit",question="Logo'da Eylül 2026 için gerçek satılan mal maliyeti ve iade maliyetiyle kesin brüt kârı hesapla; son alış fiyatını gerçek maliyet yerine kullanma.",start=START,end=END,boundary="ACTUAL_COST_UNVERIFIED"),
    ]
    return out


def stock_reference(reader,case):
    history=case["mode"]=="stock_history"
    end=case.get("end") or str(date.fromisoformat(case["as_of"])+timedelta(days=1))
    cards=reader.read("SELECT LOGICALREF,CODE,NAME FROM dbo.LG_411_ITEMS WHERE LTRIM(RTRIM(CODE))="+quote(case["book"]))
    if len(cards)!=1:raise RuntimeError("Reference book code no longer unique")
    item=cards[0];ref=int(item["LOGICALREF"])
    source=reader.read(f"SELECT INVENNO,CONVERT(varchar(10),DATE_,23) DAY_,ONHAND FROM dbo.LV_411_01_STINVTOT WHERE STOCKREF={ref} AND INVENNO>=0 AND DATE_<{quote(end)}")
    movements=reader.read(f"SELECT SOURCEINDEX,CONVERT(varchar(10),DATE_,23) DAY_,IOCODE,AMOUNT,UINFO1,UINFO2 FROM dbo.LG_411_01_STLINE WHERE STOCKREF={ref} AND SOURCEINDEX>=0 AND LINETYPE=0 AND CANCELLED=0 AND DATE_<{quote(end)}")
    vendor=defaultdict(Decimal);ledger=defaultdict(Decimal);bad=set()
    for r in source:vendor[(r["INVENNO"],r["DAY_"] if history else None)]+=D(r["ONHAND"])
    for r in movements:
        key=(r["SOURCEINDEX"],r["DAY_"] if history else None)
        direction={1:1,2:1,3:-1,4:-1}.get(r["IOCODE"])
        if direction is None or r["UINFO1"] is None or r["UINFO2"] is None or r["UINFO1"]<=0 or r["UINFO1"]!=r["UINFO2"]:bad.add(key)
        ledger[key]+=D(r["AMOUNT"])*(direction or 0)
    output=[];running=defaultdict(Decimal);poisoned=set()
    for key in sorted(set(vendor)|set(ledger),key=lambda k:(k[0],str(k[1] or ""))):
        wh,day=key;v=vendor[key];m=ledger[key];good=key not in bad and abs(v-m)<=Decimal("0.000001")
        row=dict(stock_ref=ref,book_code=case["book"],book_name=item["NAME"],warehouse_no=wh,onhand=v if good else None,source_quantity=v,movement_quantity=m,reconciliation="MATCHED" if good else "UNVERIFIED")
        if history:
            if not good:poisoned.add(wh)
            else:running[wh]+=v
            row.update(day=day,daily_change=v if good else None,onhand=None if wh in poisoned else running[wh])
            if day is None or not case["start"]<=day<case["end"]:continue
        output.append(row)
    return output, bool(bad or any(r["reconciliation"]!="MATCHED" for r in output))


def reference(reader,case):
    mode=case["mode"]
    if mode in ("stock","stock_history"):return stock_reference(reader,case)
    if case.get("boundary"):return [],True
    if mode=="open_orders":
        sql="SELECT O.LOGICALREF,H.LOGICALREF header_ref,H.FICHENO,O.DATE_,I.CODE book_code,I.NAME book_name,C.CODE customer_code,C.DEFINITION_ customer_name,O.SOURCEINDEX,O.UOMREF,O.UINFO1,O.UINFO2,O.AMOUNT,O.SHIPPEDAMOUNT,O.LINENET,O.DUEDATE FROM dbo.LG_411_01_ORFLINE O LEFT JOIN dbo.LG_411_01_ORFICHE H ON H.LOGICALREF=O.ORDFICHEREF JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=O.STOCKREF LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=O.CLIENTREF WHERE O.TRCODE=1 AND O.LINETYPE=0 AND O.CANCELLED=0 AND (H.CANCELLED=0 OR H.LOGICALREF IS NULL) AND O.CLOSED=0 AND O.AMOUNT>O.SHIPPEDAMOUNT AND O.DATE_>='20260101' AND O.DATE_<'20261001' AND LTRIM(RTRIM(I.CODE))="+quote(case["book"])
        rows=[];partial=False
        for r in reader.read(sql):
            if r["header_ref"] is None:partial=True;continue
            qty=D(r["AMOUNT"])-D(r["SHIPPEDAMOUNT"])
            main=qty if r["UINFO1"] and r["UINFO1"]==r["UINFO2"] else None
            due=str(r["DUEDATE"])[:10] if r["DUEDATE"] and str(r["DUEDATE"])[:10]>="1900-01-01" else None
            rows.append(dict(source_period="411/01",order_line_ref=r["LOGICALREF"],order_number=r["FICHENO"],order_date=str(r["DATE_"])[:10],book_code=str(r["book_code"]).strip(),book_name=r["book_name"],customer_code=r["customer_code"],customer_name=r["customer_name"],warehouse_no=r["SOURCEINDEX"],unit_ref=r["UOMREF"],ordered_quantity=r["AMOUNT"],shipped_quantity=r["SHIPPEDAMOUNT"],remaining_quantity=qty,remaining_base_quantity=main,remaining_net_amount_proportional=D(r["LINENET"])*qty/D(r["AMOUNT"]),due_date=due,overdue_days=max(0,(date.fromisoformat(AS_OF)-date.fromisoformat(due)).days) if due else None))
            partial|=main is None
        return rows,partial
    if mode in ("customer_balances","payment_movements"):
        rows=reader.read("SELECT C.CODE,C.DEFINITION_,C.TAXNR,L.DATE_,L.SIGN,L.TRCODE,L.AMOUNT FROM dbo.LG_411_01_CLFLINE L JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE C.CODE LIKE '120%' AND C.CODE="+quote(case["customer"])+" AND L.CANCELLED=0 AND L.DATE_<'20261001'")
        groups={}
        types={1:"cash",20:"bank",61:"cheque",62:"promissory_note",70:"card"}
        for r in rows:
            stamp=str(r["DATE_"])[:10];amount=D(r["AMOUNT"])
            if mode=="payment_movements":
                if stamp<START or r["SIGN"]!=1 or r["TRCODE"] not in types:continue
                key=(r["CODE"],r["DEFINITION_"],r["TRCODE"])
                item=groups.setdefault(key,dict(customer_code=key[0],customer_name=key[1],payment_code=key[2],payment_type=types[key[2]],movement_count=0,payment_amount=Decimal(0)))
                item["movement_count"]+=1;item["payment_amount"]+=amount
            else:
                key=(r["CODE"],r["DEFINITION_"],(r["TAXNR"] or "").strip() or None)
                item=groups.setdefault(key,dict(customer_code=key[0],customer_name=key[1],tax_number=key[2],opening_balance=Decimal(0),period_debits=Decimal(0),period_credits=Decimal(0),closing_balance=Decimal(0),unverified_sign_rows=0))
                if r["SIGN"] not in (0,1):item["unverified_sign_rows"]+=1;continue
                signed=amount if r["SIGN"]==0 else -amount;item["closing_balance"]+=signed
                if stamp<START:item["opening_balance"]+=signed
                elif r["SIGN"]==0:item["period_debits"]+=amount
                else:item["period_credits"]+=amount
        partial=False
        if mode=="customer_balances":
            for r in groups.values():
                if r["unverified_sign_rows"]:
                    partial=True
                    for name in ("opening_balance","period_debits","period_credits","closing_balance"):r[name]=None
        return list(groups.values()),partial
    if mode=="currencies":
        labels={r["CURTYPE"]:r["CURCODE"] for r in reader.read("SELECT CURTYPE,CURCODE FROM L_CURRENCYLIST WHERE FIRMNR=411")}
        rows=reader.read("SELECT TRCURR,TRCODE,NETTOTAL,TRNET FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE IN (2,3,7,8,9) AND DATE_>='20260901' AND DATE_<'20261001'")
        groups={};invalid=set()
        for r in rows:
            key=(r["TRCURR"],labels.get(r["TRCURR"]))
            item=groups.setdefault(key,dict(currency_id=key[0],currency_code=key[1],invoice_count=0,local_invoice_net=Decimal(0),original_invoice_net=Decimal(0)))
            sign=-1 if r["TRCODE"] in (2,3) else 1
            item["invoice_count"]+=1;item["local_invoice_net"]+=sign*D(r["NETTOTAL"]);item["original_invoice_net"]+=sign*D(r["TRNET"])
            if key[1] is None or r["TRNET"] is None or abs(D(r["NETTOTAL"]))>Decimal("0.000001") and abs(D(r["TRNET"]))<Decimal("0.000001"):invalid.add(key)
        for key in invalid:groups[key]["original_invoice_net"]=None
        return list(groups.values()),bool(invalid)
    if mode=="purchase_prices":
        rows=reader.read("SELECT I.CODE book_code,I.NAME book_name,C.CODE supplier_code,C.DEFINITION_ supplier_name,S.DATE_,S.UOMREF,S.UINFO1,S.UINFO2,S.TRCURR,S.AMOUNT,S.LINENET FROM dbo.LG_411_01_STLINE S JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=S.STOCKREF LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=S.CLIENTREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE=1 AND S.DATE_>='20260901' AND S.DATE_<'20261001' AND LTRIM(RTRIM(I.CODE))="+quote(case["book"]))
        groups={};keys=case["keys"]
        for r in rows:
            item=dict(book_code=str(r["book_code"]).strip(),book_name=r["book_name"],supplier_code=r["supplier_code"],supplier_name=r["supplier_name"],month=str(r["DATE_"])[:7],unit_source="411",unit_ref=r["UOMREF"],unit_factor_1=r["UINFO1"],unit_factor_2=r["UINFO2"],transaction_currency_id=r["TRCURR"])
            key=tuple(item[k] for k in keys);group=groups.setdefault(key,dict(item,purchase_quantity=Decimal(0),purchase_net_amount=Decimal(0)))
            group["purchase_quantity"]+=D(r["AMOUNT"]);group["purchase_net_amount"]+=D(r["LINENET"])
        for r in groups.values():r["weighted_unit_purchase_price"]=r["purchase_net_amount"]/r["purchase_quantity"] if r["purchase_quantity"] else None
        return list(groups.values()),False
    raise ValueError("Unknown reference capability")


def strict_numeric_errors(case,actual,expected):
    left={tuple(r.get(k) for k in case["keys"]):r for r in actual}
    right={tuple(r.get(k) for k in case["keys"]):r for r in expected}
    errors=[]
    for key in set(left)&set(right):
        for field in QUANTITY_COLUMNS | {"weighted_unit_purchase_price", "movement_count", "unverified_sign_rows"}:
            a,b=left[key].get(field),right[key].get(field)
            if a is None or b is None:continue
            tolerance=Decimal("0") if field in ("movement_count","unverified_sign_rows") else Decimal("0.000001") if field=="weighted_unit_purchase_price" else Decimal("0.000000001")
            if abs(D(a)-D(b))>tolerance:errors.append("Numeric mismatch: "+field)
    return errors


def compare(case,answer,whole,expected,partial):
    plan=(answer.get("semantic") or {}).get("plan",{}).get("logo_report") or {}
    errors=[]
    if plan.get("mode")!=case["mode"]:errors.append("Wrong report mode")
    for src,dest in (("book","book_code"),("customer","customer_code"),("start","start"),("end","end"),("as_of","as_of")):
        if case.get(src) is not None and plan.get(dest)!=case[src]:errors.append("Wrong report scope: "+dest)
    if case.get("boundary"):
        gaps=answer.get("gaps",[]) or answer.get("semantic",{}).get("gaps",[])
        if answer.get("type")!="PARTIAL_ANSWER" or not any(g.get("code")==case["boundary"] for g in gaps):errors.append("Expected explicit verified-definition boundary")
        if whole.get("records"):errors.append("Boundary fabricated numeric results")
        return errors
    wanted="PARTIAL_ANSWER" if partial else "TEXT_TO_SQL"
    if answer.get("type")!=wanted:errors.append("Wrong answer completeness/type")
    adapted={**answer,"type":"TEXT_TO_SQL"}
    errors+=transport.compare({**case,"source":"report"},adapted,whole,expected)
    errors+=strict_numeric_errors(case,whole.get("records",[]),expected)
    if partial and not (answer.get("gaps") or answer.get("semantic",{}).get("gaps")):errors.append("Missing explicit partial-result gap")
    return errors


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",required=True);parser.add_argument("--only",default="");parser.add_argument("--base",default="http://127.0.0.1:8795");args=parser.parse_args()
    if sys.platform!="linux" or not transport.ROOT.is_dir():raise SystemExit("Remote connected test-server runs only")
    if str(datetime.now(ZoneInfo("Europe/Istanbul")).date())!=AS_OF:raise SystemExit("Corpus dates require2026-09-30; do not silently alter current order-state reference")
    if not args.base.startswith("http://127.0.0.1:"):raise SystemExit("Loopback test-server API required")
    os.umask(0o077);lock=open('/tmp/finance-composable-live.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit("Another finance acceptance run is active")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if (out/'report.json').exists():raise SystemExit("Use fresh evidence output")
    session=None;digest=None;conn=None;removed=0;results=[];counts=Counter();before=transport.manifest();selected=[]
    def interrupt(signum,frame):raise KeyboardInterrupt(f"signal{signum}")
    signal.signal(signal.SIGTERM,interrupt)
    try:
        env=transport.environment('nanobase-semantic-bridge');login=transport.environment('timas-login')
        if env.get('FINANCE_QUERY_MODE')!='contract':raise RuntimeError("Contract mode not active")
        conn=transport.connect('/data/nanobaseai/bi/secrets/logo-mssql-connection.json');reader=Reader(conn)
        anchors=seed(reader);transport.save(out/'reference-anchors.json',dict(anchors=anchors,queries=reader.evidence))
        selected=[c for c in cases(anchors) if not args.only or c['id'] in args.only.split(',')]
        if not selected:raise RuntimeError("No selected cases")
        session=sqlite3.connect(login.get('SESSION_DB','/var/lib/timas-login/sessions.sqlite'))
        token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
        session.execute('INSERT INTO sessions(token,username,expires) VALUES(?,?,?)',(digest,'timasai',time.time()+900));session.commit()
        headers={'Content-Type':'application/json','X-Semantic-Caller':env.get('SEMANTIC_CALLER_TOKEN',''),'Cookie':('__Secure-timas_session' if login.get('COOKIE_SECURE','1')!='0' else 'timas_session')+'='+token}
        def call(path,body=None):
            req=urllib.request.Request(args.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            with urllib.request.urlopen(req,timeout=180) as response:return json.load(response)
        expected_hash=hashlib.sha256(json.dumps({k.rsplit('/',1)[-1]:v for k,v in before.items() if '/finance_query/' in k},sort_keys=True).encode()).hexdigest()
        for case in selected:
            item={**case,'started':time.time()};stop=False;offset=len(transport.REFERENCE_RETRIES)
            try:
                if case.get('requires') and not anchors.get(case['requires']):raise RuntimeError('No real source anchor for this case')
                session.execute('UPDATE sessions SET expires=? WHERE token=?',(time.time()+900,digest));session.commit()
                transport.REFERENCE_CONTEXT.clear();transport.REFERENCE_CONTEXT.update(caseId=case['id'],phase='before_api',source='logo')
                reader.evidence=[];expected,partial=reference(reader,case);item.update(reference=expected,referenceQueries=reader.evidence,expectedPartial=partial)
                answer=call('/api/v1/ask',{'question':case['question'],'sampleSize':7});item['answer']=answer
                whole=call('/api/v1/result/'+answer['resultId']) if answer.get('resultId') else answer;item['fullResult']=whole
                errors=compare(case,answer,whole,expected,partial)
                if answer.get('semantic',{}).get('engine')!='finance_contract_v1':errors.append('Wrong engine')
                if answer.get('semantic',{}).get('engineCodeHash')!=expected_hash:errors.append('Wrong loaded engine hash')
                item['errors']=errors;item['status']='FAIL' if errors else 'BOUNDARY_PASS' if case.get('boundary') else 'PARTIAL_REFERENCE_MATCH' if partial else 'PASS'
                if not case.get('boundary'):
                    transport.REFERENCE_CONTEXT['phase']='after_api';reader.evidence=[]
                    after_ref,after_partial=reference(reader,case);item.update(referenceAfter=after_ref,referenceAfterQueries=reader.evidence)
                    if partial!=after_partial or not transport.references_equal(case,expected,after_ref) or strict_numeric_errors(case,expected,after_ref):
                        item['referenceChanged']=True
                        structural=[e for e in errors if not transport.data_dependent_error(e)]
                        item['status']='FAIL' if structural else 'UNVERIFIED'
            except Exception as exc:
                structural=[e for e in item.get('errors',[]) if not transport.data_dependent_error(e)]
                item['status']='FAIL' if structural else 'UNVERIFIED';item['error']=type(exc).__name__+': '+str(exc)[:500]
                stop=isinstance(exc,TimeoutError) or isinstance(exc,urllib.error.URLError) and isinstance(exc.reason,TimeoutError)
            item['referenceRetries']=transport.REFERENCE_RETRIES[offset:];item['elapsedSeconds']=round(time.time()-item['started'],2)
            transport.save(out/(case['id']+'.json'),item);counts[item['status']]+=1
            results.append({k:item[k] for k in ('id','status','errors','error','elapsedSeconds') if k in item})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            if len(results)%10==0:print('BATCH',len(results),dict(counts),flush=True)
            if stop:print('STOP: timed out request may still execute; no duplicate run',flush=True);break
    except BaseException as exc:
        counts['UNVERIFIED']+=1;results.append(dict(id='ENVIRONMENT',status='UNVERIFIED',error=type(exc).__name__+': '+str(exc)[:500]))
    finally:
        if conn is not None:
            try:conn.close()
            except Exception:pass
        if session is not None:
            try:
                if digest:removed=session.execute('DELETE FROM sessions WHERE token=?',(digest,)).rowcount;session.commit()
            except Exception as exc:counts['UNVERIFIED']+=1;results.append(dict(id='SESSION_CLEANUP',status='UNVERIFIED',error=str(exc)[:300]))
            finally:session.close()
        after=transport.manifest()
        if before!=after:counts['UNVERIFIED']+=1;results.append(dict(id='CODE_CHANGED',status='UNVERIFIED'))
        report=dict(api=args.base,executionEnvironment='connected real test server',referenceDate=AS_OF,counts=dict(counts),results=results,planned=len(selected),completed=sum(r['id'].startswith('LR') for r in results),codeStable=before==after,codeBefore=before,codeAfter=after,sessionsDeleted=removed,sourceWrites=0,boundaryPassIsNumericAcceptance=False,partialReferenceMatchIsFullAcceptance=False,referenceRetryIsProductRecoveryEvidence=False,runnerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        transport.save(out/'report.json',report);print('FINAL',dict(counts),'sessionsDeleted',removed,flush=True)
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    return 1 if counts['FAIL'] or counts['UNVERIFIED'] or counts['PARTIAL_REFERENCE_MATCH'] or report['completed']!=len(selected) else 0


if __name__=='__main__':raise SystemExit(main())
