"""Run the user's exact complex prompts against the connected real application.

Execution evidence only. A successful HTTP/SQL result is never a correctness PASS.
Use fresh output directories; do not mix answers from different code versions.
"""
import argparse
from collections import Counter
from datetime import datetime
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

from composable_live import ROOT, environment, connect, query, manifest, save


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--questions",required=True);parser.add_argument("--out",required=True);parser.add_argument("--only",default="")
    args=parser.parse_args()
    if sys.platform!="linux" or not ROOT.is_dir():raise SystemExit("Connected test server only; local tests prohibited")
    os.umask(0o077)
    lock=open("/tmp/finance-composable-live.lock","a")
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    out=Path(args.out)
    if out.exists() and any(out.iterdir()):raise SystemExit("Use a fresh evidence directory")
    out.mkdir(parents=True,exist_ok=True)
    content=Path(args.questions).read_bytes();question_pack=json.loads(content);questions=question_pack["questions"]
    reference_date=question_pack["referenceDate"]
    if str(datetime.now(ZoneInfo("Europe/Istanbul")).date())!=reference_date:
        raise SystemExit("Reference date differs from live planner date; review relative-date expectations explicitly")
    if len(questions)!=100 or len({x["id"] for x in questions})!=100:raise SystemExit("Expected the exact 100 unique cases")
    if args.only:questions=[x for x in questions if x["id"] in args.only.split(",")]
    before=manifest();results=[];counts=Counter();session=None;digest=None;removed=0
    def report():
        after=manifest()
        return dict(api="http://127.0.0.1:8795",executionEnvironment="connected test server",counts=dict(counts),results=results,planned=len(questions),completed=len(results),codeBefore=before,codeAfter=after,codeStable=before==after,sessionsDeleted=removed,sourceWrites=0,correctnessPass=0,questionFileSha256=hashlib.sha256(content).hexdigest(),runnerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),note="Execution and answer delivery only; independent full-answer references are required for correctness acceptance")
    def interrupt(signum,frame):raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM,interrupt)
    try:
        env=environment("nanobase-semantic-bridge");login=environment("timas-login")
        preflight={}
        for source in ("logo","crm"):
            conn=connect(f"/data/nanobaseai/bi/secrets/{source}-mssql-connection.json")
            try:preflight[source]=query(conn,"SELECT DB_NAME() database_name, CONVERT(varchar(33),GETDATE(),126) database_time")
            finally:conn.close()
        save(out/"preflight.json",preflight)
        session=sqlite3.connect(login.get("SESSION_DB","/var/lib/timas-login/sessions.sqlite"))
        token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
        session.execute("INSERT INTO sessions(token,username,expires) VALUES(?,?,?)",(digest,"timasai",time.time()+900));session.commit()
        headers={"Content-Type":"application/json","X-Semantic-Caller":env.get("SEMANTIC_CALLER_TOKEN",""),"Cookie":("__Secure-timas_session" if login.get("COOKIE_SECURE","1")!="0" else "timas_session")+"="+token}
        def call(path,body=None):
            req=urllib.request.Request("http://127.0.0.1:8795"+path,data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers=headers)
            with urllib.request.urlopen(req,timeout=240) as response:return json.load(response)
        call("/health")
        engine_hash=hashlib.sha256(json.dumps({k.rsplit('/',1)[-1]:v for k,v in before.items() if '/finance_query/' in k},sort_keys=True).encode()).hexdigest()
        for case in questions:
            if str(datetime.now(ZoneInfo("Europe/Istanbul")).date())!=reference_date:
                raise RuntimeError("Local date changed; acceptance stopped before relative questions could silently shift")
            if manifest()!=before:raise RuntimeError("Deployed code changed; acceptance stopped before another question")
            session.execute("UPDATE sessions SET expires=? WHERE token=?",(time.time()+900,digest));session.commit()
            item={**case,"started":time.time()};stop=False
            try:
                answer=call("/api/v1/ask",dict(question=case["question"],sampleSize=7,threadId="complex100-"+case["id"]+"-"+secrets.token_hex(6)))
                item["answer"]=answer;kind=answer.get("type","UNKNOWN");item["answerType"]=kind
                item["status"]={"CLARIFICATION":"NEEDS_CLARIFICATION","PARTIAL_ANSWER":"PARTIAL_UNVERIFIED","UNSUPPORTED_CAPABILITY":"UNSUPPORTED","DATA_SOURCE_UNAVAILABLE":"SOURCE_ERROR","PLAN_INVALID":"PLAN_ERROR","SOURCE_CONTRACT_VIOLATION":"SOURCE_CONTRACT_ERROR","TEXT_TO_SQL":"ANSWER_UNVERIFIED"}.get(kind,kind)
                semantic=answer.get("semantic",{})
                if semantic.get("engine")!="finance_contract_v1" or semantic.get("engineCodeHash")!=engine_hash:raise RuntimeError("Wrong engine or loaded code version")
                if semantic.get("legacyCatalogUsed") is not False or semantic.get("legacySqlFallback") is not False:raise RuntimeError("Legacy path not retired")
                if answer.get("resultId"):
                    full=call("/api/v1/result/"+answer["resultId"]);item["fullResult"]=full
                    if full.get("id")!=answer["resultId"] or full.get("truncated") is not False:raise RuntimeError("Same execution full result unavailable")
                    if full.get("totalRows")!=len(full.get("records",[])) or answer.get("rowCount")!=full.get("totalRows"):raise RuntimeError("Full-result row count mismatch")
                    if answer.get("records")!=full["records"][:answer.get("shownRows",0)]:raise RuntimeError("Preview does not match same execution")
                    for section in full.get("sections",[]):
                        if section.get("totalRows")!=len(section.get("records",[])) or section.get("truncated") is not False:raise RuntimeError("Incomplete stored section")
            except Exception as exc:
                item["status"]="EXECUTION_ERROR";item["error"]=type(exc).__name__+": "+str(exc)[:700]
                stop=isinstance(exc,(TimeoutError,urllib.error.URLError)) or "code version" in str(exc)
            item["elapsedSeconds"]=round(time.time()-item["started"],2)
            save(out/(case["id"]+".json"),item)
            summary={k:v for k,v in item.items() if k not in ("answer","fullResult")};results.append(summary);counts[item["status"]]+=1
            save(out/"report.json",report());print(json.dumps(summary,ensure_ascii=False),flush=True)
            if len(results)%10==0:print("BATCH",len(results),dict(counts),flush=True)
            if stop:break
    finally:
        if session is not None:
            if digest:removed=session.execute("DELETE FROM sessions WHERE token=?",(digest,)).rowcount;session.commit()
            session.close()
        save(out/"report.json",report());print("FINAL",dict(counts),"sessionsDeleted",removed,flush=True)
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    return 0 if len(results)==len(questions) and not counts["EXECUTION_ERROR"] else 1


if __name__=="__main__":raise SystemExit(main())
