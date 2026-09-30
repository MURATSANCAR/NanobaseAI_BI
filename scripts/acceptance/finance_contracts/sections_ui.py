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
try:
    case=next(c for c in gate.cases() if c.get("sections"))
    login=gate.environment("timas-login")
    session=sqlite3.connect(login.get("SESSION_DB","/var/lib/timas-login/sessions.sqlite"))
    token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
    session.execute("INSERT INTO sessions(token,username,expires) VALUES(?,?,?)",(digest,"timasai",time.time()+900));session.commit()
    conn=gate.connect("/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
    try:expected=gate.reference(case,conn)
    finally:conn.close()
    subprocess.run(["node",str(Path(__file__).with_name("ui.cjs"))],env={**os.environ,"FINANCE_UI_TOKEN":token,"FINANCE_UI_OUT":str(out),"FINANCE_UI_QUESTION":case["question"]},check=True,timeout=480)
    answer=json.loads((out/"answer.json").read_text());full=json.loads((out/"full.json").read_text())
    errors=gate.compare(case,answer,full,expected)
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
    conn=gate.connect("/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
    try:after_reference=gate.reference(case,conn)
    finally:conn.close()
    stable=gate.references_equal(case,expected,after_reference)
    if gate.manifest()!=before:errors.append("Deployed code changed during acceptance")
    report.update(status="FAIL" if errors else "PASS" if stable else "UNVERIFIED",errors=errors,referenceStable=stable,case=case,reference=expected,referenceAfter=after_reference,browser=json.loads((out/"browser.json").read_text()))
except Exception as exc:report["error"]=type(exc).__name__+": "+str(exc)[:700]
finally:
    if session is not None:
        if digest:report["sessionsDeleted"]=session.execute("DELETE FROM sessions WHERE token=?",(digest,)).rowcount;session.commit()
        session.close()
    report["codeBefore"]=before;report["codeAfter"]=gate.manifest();gate.save(out/"report.json",report)
    print(json.dumps({k:v for k,v in report.items() if k not in ("reference","referenceAfter","codeBefore","codeAfter")},ensure_ascii=False,default=str),flush=True)
    fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
raise SystemExit(0 if report["status"]=="PASS" else 1)
