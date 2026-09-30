"""Remote real portal section/CSV acceptance with independent DB references."""
import csv
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
from decimal import Decimal
import composable_live as gate

if sys.platform != "linux" or not gate.ROOT.is_dir():raise SystemExit("Connected test server only")
os.umask(0o077)
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
lock=open("/tmp/finance-composable-live.lock","a");fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
session=None;digest=None;report={"status":"UNVERIFIED","sourceWrites":0};before=gate.manifest()
errors=[];phase="setup"
try:
    case=dict(id="UI_SECTIONS_FULL",question="Eylül 2026 KDV hariç iadeler düşülmüş net satışını iki ayrı tabloda göster: ilk tablo kitap kodu ve kitap adına göre, ikinci tablo kanallara göre olsun. Her iki tablonun bütün satırlarını ver; ilk N sınırı istemiyorum.",
        source="logo",columns=["section","status","row_count"],keys=["section"],periods=[],sections=[
            dict(source="logo",metrics=["net_sales"],dimensions=["book"],columns=["book_code","book_name","net_sales"],keys=["book_code","book_name"],periods=[["2026-09-01","2026-10-01"]],
                referenceSql="SELECT LTRIM(RTRIM(I.CODE)) book_code,I.NAME book_name,SUM(CASE WHEN S.TRCODE IN (2,3) THEN -S.LINENET ELSE S.LINENET END) net_sales FROM dbo.LG_411_01_STLINE S LEFT JOIN dbo.LG_411_ITEMS I ON I.LOGICALREF=S.STOCKREF WHERE S.CANCELLED=0 AND S.LINETYPE=0 AND S.INVOICEREF<>0 AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_>='20260901' AND S.DATE_<'20261001' GROUP BY LTRIM(RTRIM(I.CODE)),I.NAME"),
            dict(source="logo",metrics=["net_sales"],dimensions=["channel"],columns=["channel","net_sales"],keys=["channel"],periods=[["2026-09-01","2026-10-01"]],referenceSql=gate.sales_sql("2026-09-01","2026-10-01",["net_sales"],"channel")),
        ])
    login=gate.environment("timas-login")
    session=sqlite3.connect(login.get("SESSION_DB","/var/lib/timas-login/sessions.sqlite"))
    token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
    session.execute("INSERT INTO sessions(token,username,expires) VALUES(?,?,?)",(digest,"timasai",time.time()+900));session.commit()
    conn=gate.connect("/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
    try:expected=gate.reference(case,conn)
    finally:conn.close()
    phase="browser"
    subprocess.run(["node",str(Path(__file__).with_name("ui.cjs"))],env={**os.environ,"FINANCE_UI_TOKEN":token,"FINANCE_UI_OUT":str(out),"FINANCE_UI_QUESTION":case["question"]},check=True,timeout=480)
    phase="stored_result"
    answer=json.loads((out/"answer.json").read_text());full=json.loads((out/"full.json").read_text())
    errors=gate.compare(case,answer,full,expected)
    phase="source_coverage"
    if not any(len(section)>50 for section in expected["sections"]):
        raise RuntimeError("Real source did not exercise section pagination")
    phase="csv"
    for index,section in enumerate(full.get("sections",[])):
        with (out/f"section-{index}.csv").open(encoding="utf-8-sig",newline="") as stream:exported=list(csv.reader(stream,delimiter=";"))
        if len(exported)!=len(section["records"])+1:errors.append("CSV row count mismatch")
        for csvrow,row in zip(exported[1:],section["records"]):
            if len(csvrow)!=len(section["columns"]):errors.append("CSV column count mismatch");continue
            for cell,col in zip(csvrow,section["columns"]):
                value=row[col["name"]]
                if value is None:
                    if cell!="":errors.append("CSV NULL mismatch")
                elif isinstance(value,(int,float)) and not isinstance(value,bool):
                    if Decimal(cell)!=Decimal(str(value)):errors.append("CSV numeric mismatch")
                else:
                    text=str(value)
                    if text.lstrip()[:1] in ("=","+","@","-"):text="'"+text
                    if cell!=text:errors.append("CSV text mismatch")
    phase="after_reference"
    conn=gate.connect("/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
    try:after_reference=gate.reference(case,conn)
    finally:conn.close()
    stable=gate.references_equal(case,expected,after_reference)
    if gate.manifest()!=before:errors.append("Deployed code changed during acceptance")
    # A changed independent reference can explain only full-answer row/value
    # discrepancies. CSV is compared with the same stored execution, so even
    # CSV numeric errors remain structural failures under source drift.
    structural=[error for error in errors if not gate.data_dependent_error(error)]
    status=("FAIL" if errors else "PASS") if stable else ("FAIL" if structural else "UNVERIFIED")
    phase="browser_evidence"
    report.update(status=status,errors=errors,referenceStable=stable,referenceChanged=not stable,case=case,reference=expected,referenceAfter=after_reference,browser=json.loads((out/"browser.json").read_text()))
    if not stable and structural:report["structuralErrorsDespiteSourceChange"]=structural
except Exception as exc:
    if isinstance(exc,subprocess.CalledProcessError):errors.append("Browser acceptance process failed")
    elif phase in {"stored_result","csv","browser_evidence"}:errors.append("Result delivery evidence failure during "+phase)
    structural=[error for error in errors if not gate.data_dependent_error(error)]
    report.update(status="FAIL" if structural else "UNVERIFIED",errors=errors,error=type(exc).__name__+": "+str(exc)[:700],failurePhase=phase)
    if structural:report["structuralErrorsDespiteIncompleteVerification"]=structural
finally:
    if session is not None:
        if digest:report["sessionsDeleted"]=session.execute("DELETE FROM sessions WHERE token=?",(digest,)).rowcount;session.commit()
        session.close()
    report["codeBefore"]=before;report["codeAfter"]=gate.manifest();gate.save(out/"report.json",report)
    print(json.dumps({k:v for k,v in report.items() if k not in ("reference","referenceAfter","codeBefore","codeAfter")},ensure_ascii=False,default=str),flush=True)
    fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
raise SystemExit(0 if report["status"]=="PASS" else 1)
