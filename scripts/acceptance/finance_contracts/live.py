"""Run ONLY on the test server. Real API + independent direct SQL; no production compiler imports.

sudo semantic-venv/bin/python scripts/acceptance/finance_contracts/live.py --out /tmp/<session>/acceptance
The temporary timasai session is deleted in finally. Questions use separate conversations.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error

import pyodbc


def environment(unit):
    pid = subprocess.check_output(["systemctl", "show", unit, "-p", "MainPID", "--value"], text=True).strip()
    return dict(x.split("=", 1) for x in Path(f"/proc/{pid}/environ").read_text().split("\0") if "=" in x)


def connect(path):
    cfg = json.loads(Path(path).read_text())
    def esc(v):
        return "{" + str(v).replace("}", "}}") + "}"
    values = {"DRIVER": cfg.get("driver", "FreeTDS"), "SERVER": cfg["host"], "PORT": cfg.get("port",1433),
              "DATABASE": cfg["database"], "UID": cfg["user"], "PWD": cfg["password"], "TDS_Version": cfg.get("tds_version", "7.4")}
    return pyodbc.connect(";".join(k+"="+esc(v) for k,v in values.items()), timeout=15, autocommit=True)


def query(conn, sql):
    cur=conn.cursor()
    try:
        cur.execute(sql)
        cols=[c[0] for c in cur.description]
        rows=cur.fetchmany(250001)
        if len(rows)>250000:raise RuntimeError("reference truncated")
        return [dict(zip(cols,row)) for row in rows]
    finally:cur.close()


def cases():
    # Independent references: header count never derives from the generated application's SQL.
    out=[]
    def add(q, source, sql, columns, keys=()):
        out.append({"id":f"FC{len(out)+1:02d}","question":q,"source":source,"referenceSql":sql,"columns":columns,"keys":keys})
    day="DATE_ >= '20260929' AND DATE_ < '20260930'"
    add("29 Eylül 2026 tarihinde satılan kitap adedi kaçtır?","logo",f"SELECT COALESCE(SUM(AMOUNT),0) sold_quantity FROM dbo.LG_411_01_STLINE WHERE CANCELLED=0 AND LINETYPE=0 AND INVOICEREF<>0 AND TRCODE IN (7,8) AND {day}",["sold_quantity"])
    add("29 Eylül 2026 tarihinde toptan satış faturası sayısı kaçtır?","logo",f"SELECT COUNT(*) invoice_count FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE=8 AND {day}",["invoice_count"])
    add("29 Eylül 2026 tarihinde perakende satış tutarı ne kadar?","logo",f"SELECT COALESCE(SUM(NETTOTAL),0) invoice_amount FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE=7 AND {day}",["invoice_amount"])
    add("29 Eylül 2026 tarihinde kanal bazında satılan kitap adedi kaçtır?","logo",f"SELECT C.SPECODE2 channel,SUM(S.AMOUNT) sold_quantity FROM dbo.LG_411_01_STLINE S LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=S.CLIENTREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (7,8) AND S.{day.replace(' AND DATE_', ' AND S.DATE_')} GROUP BY C.SPECODE2",["channel","sold_quantity"],["channel"])
    add("CRM’de aktif kitap kaydı sayısı kaçtır?","crm","SELECT COUNT(*) active_books FROM dbo.new_kitapBase WHERE statecode=0",["active_books"])
    add("CRM’de aktif yazar kişi kaydı sayısı kaçtır?","crm","SELECT COUNT(*) active_authors FROM dbo.ContactBase WHERE statecode=0 AND new_yazarmi=1",["active_authors"])
    add("CRM'de aktif cari kaydı sayısı kaçtır?","crm","SELECT COUNT(*) active_customers FROM dbo.AccountBase WHERE statecode=0",["active_customers"])
    for kind,code in [("toptan",8),("perakende",7)]:
        add(f"Eylül 2026 {kind} satış fatura toplamı nedir?","logo",f"SELECT COALESCE(SUM(NETTOTAL),0) invoice_amount FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE={code} AND DATE_>='20260901' AND DATE_<'20261001'",["invoice_amount"])
    add("Eylül 2026 müşterilerden tahsilat toplamı nedir?","logo","SELECT COALESCE(SUM(L.AMOUNT),0) collections FROM dbo.LG_411_01_CLFLINE L JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE C.CODE LIKE '120%' AND L.CANCELLED=0 AND L.SIGN=1 AND L.TRCODE IN (1,20,61,62,70) AND L.DATE_>='20260901' AND L.DATE_<'20261001'",["collections"])
    for y,f in [(2025,"211"),(2026,"411")]:
        for question,expr,key in [
            ("net satış tutarı", "CASE WHEN TRCODE IN (2,3) THEN -LINENET ELSE LINENET END", "net_sales"),
            ("net satılan adet", "CASE WHEN TRCODE IN (2,3) THEN -AMOUNT WHEN TRCODE IN (7,8) THEN AMOUNT ELSE 0 END", "net_quantity"),
            ("iade tutarı", "CASE WHEN TRCODE IN (2,3) THEN LINENET ELSE 0 END", "return_amount")]:
            add(f"Eylül {y} {question} toplamı nedir?","logo",f"SELECT COALESCE(SUM({expr}),0) {key} FROM dbo.LG_{f}_01_STLINE WHERE CANCELLED=0 AND LINETYPE=0 AND INVOICEREF<>0 AND TRCODE IN (2,3,7,8,9) AND DATE_>='{y}0901' AND DATE_<'{y}1001'",[key])
    add("1 Ocak 2027 tarihinde satılan kitap adedi nedir?",None,None,[])
    out[-1]["expected"]="clarify"
    add("29 Eylül 2026 tarihinde kitap bazında satılan adet nedir?","logo",f"SELECT LTRIM(RTRIM(I.CODE)) book_code,I.NAME book_name,SUM(L.AMOUNT) sold_quantity FROM dbo.LG_411_01_STLINE L LEFT JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=L.STOCKREF WHERE L.CANCELLED=0 AND L.LINETYPE=0 AND L.INVOICEREF<>0 AND L.TRCODE IN (7,8) AND L.{day.replace(' AND DATE_', ' AND L.DATE_')} GROUP BY I.CODE,I.NAME",["book_code","book_name","sold_quantity"],["book_code","book_name"])
    for q in ["CRM'de pasif kitap kayıtlarını say.","2026 cirosunu dolara çevir.","Vadesi geçmiş alacaklarımız kesin olarak ne kadar?","2026 satış hedefi ile gerçekleşen net satış tutarını kitap bazında karşılaştır."]:
        add(q,None,None,[]);out[-1]["expected"]="clarify"
    # Cross-source result is independently assembled from fresh raw rows below.
    add("29 Eylül 2026 satışlarını kitap, kanal, yazar ve yayınevi bazında adet ve KDV hariç satış tutarı olarak göster.","cross",None,["book_code","book_name","channel","author","publisher","sold_quantity","sales_amount"],["book_code","book_name","channel","author","publisher"])
    add("29 Eylül 2026 tarihinde toplam kaç satış faturası kesildi?","logo",f"SELECT COUNT(*) invoice_count FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE IN (7,8,9) AND {day}",["invoice_count"])
    add("Eylül 2026 günlük net satış tutarı nedir?","logo","SELECT CONVERT(varchar(10),DATE_,23) day,SUM(CASE WHEN TRCODE IN (2,3) THEN -LINENET ELSE LINENET END) net_sales FROM dbo.LG_411_01_STLINE WHERE CANCELLED=0 AND LINETYPE=0 AND INVOICEREF<>0 AND TRCODE IN (2,3,7,8,9) AND DATE_>='20260901' AND DATE_<'20261001' GROUP BY CONVERT(varchar(10),DATE_,23)",["day","net_sales"],["day"])
    for d in ["1 Ocak 2026", "15 Eylül 2026", "28 Eylül 2026", "30 Eylül 2026", "31 Aralık 2026"]:
        stamp={"1 Ocak 2026":"20260101","15 Eylül 2026":"20260915","28 Eylül 2026":"20260928","30 Eylül 2026":"20260930","31 Aralık 2026":"20261231"}[d]
        add(f"{d} tarihinde perakende satış faturası sayısı kaçtır?","logo",f"SELECT COUNT(*) invoice_count FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE=7 AND DATE_>=CONVERT(date,'{stamp}',112) AND DATE_<DATEADD(day,1,CONVERT(date,'{stamp}',112))",["invoice_count"])
    # Fresh 100-question corpus. No legacy questions, SQL, compiler, or rule catalog.
    months="Ocak Şubat Mart Nisan Mayıs Haziran Temmuz Ağustos Eylül Ekim Kasım Aralık".split()
    for year,firm in [(2025,211),(2026,411)]:
        for month,label in enumerate(months,1):
            start=f"{year}{month:02d}01";end=f"{year+(month==12)}{month%12+1:02d}01"
            add(f"{label} {year} net satış tutarı ve satılan kitap adedi toplamını ver.","logo",
                f"SELECT COALESCE(SUM(CASE WHEN TRCODE IN (2,3) THEN -LINENET ELSE LINENET END),0) net_sales,COALESCE(SUM(CASE WHEN TRCODE IN (7,8) THEN AMOUNT ELSE 0 END),0) sold_quantity FROM dbo.LG_{firm}_01_STLINE WHERE CANCELLED=0 AND LINETYPE=0 AND INVOICEREF<>0 AND TRCODE IN (2,3,7,8,9) AND DATE_>='{start}' AND DATE_<'{end}'",["net_sales","sold_quantity"])
    for month,label in enumerate(months,1):
        start=f"2026{month:02d}01";end=f"{2026+(month==12)}{month%12+1:02d}01"
        add(f"{label} 2026 toptan satış faturalarının sayısını ve fatura toplamını göster.","logo",
            f"SELECT COUNT(*) invoice_count,COALESCE(SUM(NETTOTAL),0) invoice_amount FROM dbo.LG_411_01_INVOICE WHERE CANCELLED=0 AND TRCODE=8 AND DATE_>='{start}' AND DATE_<'{end}'",["invoice_count","invoice_amount"])
    for day in range(20,30):
        add(f"{day} Eylül 2026 kanal bazında net satılan kitap adedi nedir?","logo",
            f"SELECT C.SPECODE2 channel,SUM(CASE WHEN S.TRCODE IN (2,3) THEN -S.AMOUNT ELSE S.AMOUNT END) net_quantity FROM dbo.LG_411_01_STLINE S LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=S.CLIENTREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (2,3,7,8) AND S.DATE_>='202609{day:02d}' AND S.DATE_<'202609{day+1:02d}' GROUP BY C.SPECODE2",["channel","net_quantity"],["channel"])
    for day in range(24,30):
        add(f"{day} Eylül 2026 kitap ve kanal bazında satılan adet ile KDV hariç satış tutarını göster.","logo",
            f"SELECT LTRIM(RTRIM(I.CODE)) book_code,I.NAME book_name,C.SPECODE2 channel,SUM(CASE WHEN S.TRCODE IN (7,8) THEN S.AMOUNT ELSE 0 END) sold_quantity,SUM(S.LINENET) sales_amount FROM dbo.LG_411_01_STLINE S LEFT JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=S.STOCKREF LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=S.CLIENTREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (7,8,9) AND S.DATE_>='202609{day:02d}' AND S.DATE_<'202609{day+1:02d}' GROUP BY I.CODE,I.NAME,C.SPECODE2",["book_code","book_name","channel","sold_quantity","sales_amount"],["book_code","book_name","channel"])
    for channel in ("DAGITICI","DIGER","E-TICARET","KITAPCI","KURUM","ZINCIR"):
        add(f"29 Eylül 2026 yalnız {channel} kanalındaki satılan kitap adedi toplamı nedir?","logo",
            f"SELECT COALESCE(SUM(S.AMOUNT),0) sold_quantity FROM dbo.LG_411_01_STLINE S JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=S.CLIENTREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (7,8) AND S.DATE_>='20260929' AND S.DATE_<'20260930' AND C.SPECODE2=N'{channel}'",["sold_quantity"])
    for day in range(26,30):
        add(f"{day} Eylül 2026 en çok satılan ilk 10 kitabı adetleriyle göster.","logo",
            f"SELECT TOP(10) LTRIM(RTRIM(I.CODE)) book_code,I.NAME book_name,SUM(S.AMOUNT) sold_quantity FROM dbo.LG_411_01_STLINE S LEFT JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=S.STOCKREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (7,8) AND S.DATE_>='202609{day:02d}' AND S.DATE_<'202609{day+1:02d}' GROUP BY I.CODE,I.NAME ORDER BY SUM(S.AMOUNT) DESC,I.CODE DESC,I.NAME DESC",["book_code","book_name","sold_quantity"],["book_code","book_name"])
    for month in (3,6,8,9):
        parts=[]
        for year,firm in [(2025,211),(2026,411)]:
            start=f"{year}-{month:02d}-01";end=f"{year}-{month+1:02d}-01"
            parts.append(f"SELECT '{start}' period_start,'{end}' period_end_exclusive,COALESCE(SUM(CASE WHEN TRCODE IN (2,3) THEN -LINENET ELSE LINENET END),0) net_sales FROM dbo.LG_{firm}_01_STLINE WHERE CANCELLED=0 AND LINETYPE=0 AND INVOICEREF<>0 AND TRCODE IN (2,3,7,8,9) AND DATE_>='{start}' AND DATE_<'{end}'")
        add(f"{months[month-1]} 2025 ve {months[month-1]} 2026 net satış tutarlarını dönem dönem göster.","logo"," UNION ALL ".join(parts),["period_start","period_end_exclusive","net_sales"],["period_start","period_end_exclusive"])
    for question in ("Eylül 2026 net satış tutarı 100 bin TL'den büyük kitapları listele.",
                     "2026 net satış büyüme yüzdesini hesapla.",
                     "Eylül 2026 yalnız nakit tahsilat toplamını ver.",
                     "2026 brüt kâr tutarı nedir?"):
        add(question,None,None,[]);out[-1]["expected"]="clarify"
    return out


def cross_reference(conns):
    cards=query(conns["crm"],"SELECT LTRIM(RTRIM(K.new_stokkodu)) code,K.new_yazartext author,M.new_name publisher FROM dbo.new_kitapBase K LEFT JOIN dbo.new_markaBase M ON M.new_markaId=K.new_yayineviid AND M.statecode=0 WHERE K.statecode=0 AND NULLIF(LTRIM(RTRIM(K.new_stokkodu)),'') IS NOT NULL")
    index={}
    for r in cards:
        key=r["code"].strip().casefold()
        if key in index:raise RuntimeError("independent CRM reference has duplicate key")
        index[key]=r
    raw=query(conns["logo"],"SELECT I.CODE book_code,I.NAME book_name,C.SPECODE2 channel,L.TRCODE,L.AMOUNT,L.LINENET FROM dbo.LG_411_01_STLINE L LEFT JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=L.STOCKREF LEFT JOIN dbo.LG_411_CLCARD C ON C.LOGICALREF=L.CLIENTREF WHERE L.CANCELLED=0 AND L.LINETYPE=0 AND L.INVOICEREF<>0 AND L.TRCODE IN (7,8,9) AND L.DATE_>='20260929' AND L.DATE_<'20260930'")
    groups={}
    for r in raw:
        code=(r["book_code"] or "").strip();book=index.get(code.casefold(),{})
        author=(book.get("author") or "").strip() or None
        key=(code,r["book_name"],r["channel"],author,book.get("publisher"))
        row=groups.setdefault(key,dict(zip(["book_code","book_name","channel","author","publisher"],key),sold_quantity=Decimal(0),sales_amount=Decimal(0)))
        if r["TRCODE"] in (7,8):row["sold_quantity"]+=Decimal(str(r["AMOUNT"]))
        if r["TRCODE"] in (7,8,9):row["sales_amount"]+=Decimal(str(r["LINENET"]))
    return list(groups.values())


def compare(case, answer, whole, reference):
    if case.get("expected")=="clarify":
        return [] if answer.get("type")=="CLARIFICATION" else ["expected honest clarification"]
    if answer.get("type")!="TEXT_TO_SQL":return ["expected answer: "+str(answer.get("explanation") or answer.get("error"))]
    problems=[]
    if whole.get("truncated"):problems.append("full result truncated")
    if set(c["name"] for c in whole.get("columns",[]))!=set(case["columns"]):problems.append("column identity mismatch")
    actual=whole.get("records") or []
    if len(actual)!=len(reference):problems.append(f"row count {len(actual)} != {len(reference)}")
    keys=case["keys"]
    def indexed(rows):
        out={}
        for r in rows:
            key=tuple(r.get(k) for k in keys)
            if key in out:raise ValueError("duplicate answer key")
            out[key]=r
        return out
    try:
        a,b=indexed(actual),indexed(reference)
        if set(a)!=set(b):problems.append("key set mismatch")
        for key in set(a)&set(b):
            for col in set(case["columns"])-set(keys):
                av,bv=a[key].get(col),b[key].get(col)
                if av is None or bv is None:
                    if av!=bv:problems.append(f"null mismatch {col}")
                elif abs(Decimal(str(av))-Decimal(str(bv)))>Decimal("0.01"):
                    problems.append(f"value mismatch {col}: {av} != {bv}")
    except Exception as exc:problems.append(str(exc))
    return problems[:15]


def code_manifest():
    root=Path('/data/nanobaseai/bi/frontend/backend')
    files=[root/'semantic_bridge/app.py',*sorted((root/'semantic_bridge/finance_query').glob('*.py'))]
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}


def main():
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);p.add_argument("--only",default="");p.add_argument("--repeat",type=int,default=1);p.add_argument("--base",default="http://127.0.0.1:8795");args=p.parse_args()
    if sys.platform!="linux" or not Path("/proc").is_dir():raise SystemExit("Remote real-data acceptance only")
    os.umask(0o077);out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    env=environment("nanobase-semantic-bridge");login=environment("timas-login")
    session=sqlite3.connect(login.get("SESSION_DB","/var/lib/timas-login/sessions.sqlite"));token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
    session.execute("INSERT INTO sessions(token,username,expires) VALUES(?,?,?)",(digest,"timasai",time.time()+900));session.commit()
    headers={"Content-Type":"application/json","X-Semantic-Caller":env.get("SEMANTIC_CALLER_TOKEN", ""),"Cookie":("__Secure-timas_session" if login.get("COOKIE_SECURE","1")!="0" else "timas_session")+"="+token}
    def call(path,body=None):
        req=urllib.request.Request(args.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=180) as res:return json.load(res)
    conns={};results=[];counts=Counter();passed=Counter();before=code_manifest()
    try:
        if env.get("FINANCE_QUERY_MODE")!="contract":
            raise RuntimeError("New contract engine is not active; no question sent to the legacy engine")
        for source in ("logo","crm"):conns[source]=connect(f"/data/nanobaseai/bi/secrets/{source}-mssql-connection.json")
        stopped=False
        for case in cases():
            if stopped:break
            if args.only and case["id"] not in args.only.split(","):continue
            for repeat in range(args.repeat):
                session.execute("UPDATE sessions SET expires=? WHERE token=?",(time.time()+900,digest));session.commit()
                d={**case,"repeat":repeat+1,"started":time.time()}
                try:
                    ref=cross_reference(conns) if case["source"]=="cross" else query(conns[case["source"]],case["referenceSql"]) if case.get("referenceSql") else []
                    d["reference"]=ref
                    a=call("/api/v1/ask",{"question":case["question"],"sampleSize":50});d["answer"]=a
                    whole=call("/api/v1/result/"+a["resultId"]) if a.get("resultId") else a;d["fullResult"]=whole
                    errors=compare(case,a,whole,ref)
                    if a.get("semantic",{}).get("engine")!="finance_contract_v1":errors.append("legacy engine used")
                    d["errors"]=errors;d["status"]="FAIL" if errors else "PASS"
                except Exception as exc:
                    d["status"]="UNVERIFIED";d["error"]=type(exc).__name__+": "+str(exc)[:500]
                counts[d["status"]]+=1;results.append({k:v for k,v in d.items() if k not in ("reference","answer","fullResult")})
                if d["status"]=="PASS":passed["boundary" if case.get("expected")=="clarify" else "fullAnswer"]+=1
                (out/f"{case['id']}-{repeat+1}.json").write_text(json.dumps(d,ensure_ascii=False,default=str,indent=2))
                print(json.dumps({"id":case["id"],"repeat":repeat+1,"status":d["status"],"errors":d.get("errors"),"seconds":round(time.time()-d["started"],1)},ensure_ascii=False),flush=True)
                if len(results)%10==0:print("BATCH",len(results),dict(counts),"passedKinds",dict(passed),flush=True)
                if d.get("error","").startswith("TimeoutError"):
                    print("STOP: timed out request may still be running; no duplicate workload",flush=True);stopped=True;break
    except Exception as exc:
        counts["UNVERIFIED"]+=1
        results.append({"id":"ENVIRONMENT","status":"UNVERIFIED","error":type(exc).__name__+": "+str(exc)[:500]})
    finally:
        for c in conns.values():c.close()
        removed=session.execute("DELETE FROM sessions WHERE token=?",(digest,)).rowcount;session.commit();session.close()
        after=code_manifest()
        if after!=before:
            counts["UNVERIFIED"]+=1
            results.append({"id":"CODE_CHANGED","status":"UNVERIFIED","error":"Deployed source changed during acceptance"})
        report={"counts":dict(counts),"passedKinds":dict(passed),"results":results,"sessionsDeleted":removed,"sourceWrites":0,"api":args.base,
                "codeBefore":before,"codeAfter":after,"codeStable":before==after,
                "runnerSha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,default=str,indent=2));print("FINAL",dict(counts),"sessionsDeleted",removed,flush=True)
    return 1 if counts["FAIL"] or counts["UNVERIFIED"] or not results else 0

if __name__=="__main__":raise SystemExit(main())
