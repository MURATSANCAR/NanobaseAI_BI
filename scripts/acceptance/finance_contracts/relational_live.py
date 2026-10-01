"""Remote-only independent CRM relational full-answer gate, before model tuning.

Source SQL below is authored for these acceptance intents. Never imports product
registries, SQL builders or generated SQL. IDs belong only to this test file.
No source writes. A passed execution is bounded to its frozen code and source data.
"""
import argparse
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from uuid import UUID
from zoneinfo import ZoneInfo

from composable_live import (ROOT, connect, environment, manifest, query, save,
                             require_reference_day, REFERENCE_CONTEXT, REFERENCE_RETRIES)

BOOK = "dbo.new_kitapBase B"
ACTIVE = "B.statecode=0 AND B.statuscode=1"
ISBN = "NULLIF(LTRIM(RTRIM(B.new_isbn13)),N'')"
PUB = "LEFT JOIN dbo.new_markaBase P ON P.new_markaId=B.new_yayineviid AND P.statecode=0 AND P.statuscode=1"
BRAND = "LEFT JOIN dbo.new_markaBase S ON S.new_markaId=B.new_yayinciid AND S.statecode=0 AND S.statuscode=1"
ALT = "LEFT JOIN dbo.new_yaynevialtmarkaBase A ON A.new_yaynevialtmarkaId=B.new_YayneviAltMarka AND A.statecode=0"
AUTHOR = """JOIN dbo.new_eserkatilimBase E ON E.new_Kitap=B.new_kitapId AND E.statecode=0
 JOIN dbo.new_katilimcitipiBase R ON R.new_katilimcitipiId=E.new_katilimciTipi AND R.statecode=0 AND R.new_name=N'Yazar'
 JOIN dbo.ContactBase C ON C.ContactId=E.new_Katilimsaglayan AND C.statecode=0 AND C.statuscode=1"""


def cases():
    out=[]
    def add(question,sql,columns,keys,numeric=(),pair=None,changed_from=None,join_tables=1):
        out.append(dict(id=f"RL{len(out)+1:03d}",question=question,referenceSql=sql,
                        columns=columns.split(),keys=keys.split(),numeric=list(numeric),
                        units={k:("binary_missing_flag" if k=="missing_isbn" else "book_count") for k in numeric},paraphrase_of=pair,
                        changed_from=changed_from,source_table_count=join_tables))
    sql=f"SELECT B.new_kitapId book_id,B.new_name book_name,{ISBN} isbn FROM {BOOK} WHERE {ACTIVE}"
    tail=" Kolon adları book_id, book_name, isbn olsun. Güncel ISBN alanını kullan; metin kenar boşluklarını temizle, boş ISBN'yi NULL bırak. Bütün satırlar gelsin."
    add("CRM'deki etkin kitap kartlarının kimliğini, adını ve güncel ISBN'sini listele."+tail,sql,"book_id book_name isbn","book_id")
    add("Kitap listemizi CRM'den çıkarır mısın? Etkin olanların kimlikleriyle adlarını ve güncel ISBN'lerini yan yana görmek istiyorum."+tail,sql,"book_id book_name isbn","book_id",pair="RL001")
    sql=f"SELECT B.new_kitapId book_id,CASE WHEN {ISBN} IS NULL THEN 1 ELSE 0 END missing_isbn FROM {BOOK} WHERE {ACTIVE}"
    tail=" Tüm etkin kitapları koru; ISBN boşsa 1, doluysa 0 göster. Kolonlar book_id, missing_isbn olsun; boşluklardan ibaret değeri de boş say."
    add("CRM kitaplarında güncel ISBN eksikliğini işaretle."+tail,sql,"book_id missing_isbn","book_id",numeric=["missing_isbn"])
    add("Hangi kitabın güncel ISBN'si girilmemiş, her kitap için ayrı bir gösterge istiyorum."+tail,sql,"book_id missing_isbn","book_id",numeric=["missing_isbn"],pair="RL003")
    add("CRM'de yalnız güncel ISBN'si NULL, boş veya boşluklardan ibaret olan etkin kitapları kimlik ve ham adlarıyla listele. Kolonlar book_id, book_name olsun; sınır koyma.",f"SELECT B.new_kitapId book_id,B.new_name book_name FROM {BOOK} WHERE {ACTIVE} AND {ISBN} IS NULL","book_id book_name","book_id",changed_from="RL001")
    add("CRM'nin etkin kitaplarını bugünkü etkin yayın evi kimliği ve ham adıyla gruplayıp kitap sayısını ver. Yayın evi boş veya etkin değilse NULL grubunda koru; adları aynı olan farklı kimlikleri birleştirme. Kolonlar publisher_id, publisher_name, book_count olsun.",f"SELECT P.new_markaId publisher_id,P.new_name publisher_name,COUNT_BIG(*) book_count FROM {BOOK} {PUB} WHERE {ACTIVE} GROUP BY P.new_markaId,P.new_name","publisher_id publisher_name book_count","publisher_id",numeric=["book_count"],join_tables=2)
    add("CRM'nin etkin kitaplarını bu kez bugünkü etkin alt marka kimliği ve ham adıyla grupla; new_yayinciid alanındaki alt markayı kullan. Atanmayan veya etkin olmayanı NULL grubunda koru, aynı adlı farklı kimlikleri birleştirme. Kolonlar subbrand_id, subbrand_name, book_count olsun.",f"SELECT S.new_markaId subbrand_id,S.new_name subbrand_name,COUNT_BIG(*) book_count FROM {BOOK} {BRAND} WHERE {ACTIVE} GROUP BY S.new_markaId,S.new_name","subbrand_id subbrand_name book_count","subbrand_id",numeric=["book_count"],changed_from="RL006",join_tables=2)
    for month,start,end in [("Eylül","2026-09-01","2026-10-01"),("Ağustos","2026-08-01","2026-09-01")]:
        # UTC source timestamps; Istanbul midnight is previous UTC day 21:00.
        from datetime import timedelta
        a=(date.fromisoformat(start)-timedelta(days=1)).isoformat()+"T21:00:00"
        b=(date.fromisoformat(end)-timedelta(days=1)).isoformat()+"T21:00:00"
        add(f"{month} 2026 İstanbul takvim ayında CRM'de kaydı açılmış ve şu an etkin olan kitap kartlarının toplam sayısını söyle. Yayın tarihi değil kayıt açılışını kullan. Tek kolon book_count olsun.",f"SELECT COUNT_BIG(*) book_count FROM {BOOK} WHERE {ACTIVE} AND B.CreatedOn>='{a}' AND B.CreatedOn<'{b}'","book_count","",numeric=["book_count"],changed_from="RL008" if month=="Ağustos" else None)
    add("CRM'de etkin kitaplarla etkin Yazar rolü katılımından bağlı etkin kişileri listele. Aynı kitap ve kişi birden fazla katılımda varsa bir kez göster. İsme göre eşleştirme yapma. Kolonlar book_id, book_name, person_id, person_name olsun; adlar ham kaynak değerleri olsun.",f"SELECT DISTINCT B.new_kitapId book_id,B.new_name book_name,C.ContactId person_id,C.FullName person_name FROM {BOOK} {AUTHOR} WHERE {ACTIVE}","book_id book_name person_id person_name","book_id person_id",join_tables=4)
    add("CRM'deki etkin kitapların etkin Yazar rolüyle bağlı etkin kişi yazarlarını, bugünkü yayın evi, alt marka, alternatif alt marka ve Kitap Projesi bilgileriyle yan yana göster. Her kitap-kişi çifti tek satır olsun; eksik sınıflandırmada kitabı düşürme. Kolonlar book_id, person_id, publisher_id, subbrand_id, alternate_subbrand_id, book_project_id, project_name olsun; yalnız etkin bağlı sınıflandırmaların kimliklerini göster. Alt marka new_yayinciid, alternatif alt marka new_YayneviAltMarka alanıdır. Kitap Projesi için new_KitapProjesi bağını kullan; proje adı ham değer olsun. Projesi boş veya pasifse NULL bırak.",f"SELECT DISTINCT B.new_kitapId book_id,C.ContactId person_id,P.new_markaId publisher_id,S.new_markaId subbrand_id,A.new_yaynevialtmarkaId alternate_subbrand_id,J.new_projeId book_project_id,J.new_name project_name FROM {BOOK} {AUTHOR} {PUB} {BRAND} {ALT} LEFT JOIN dbo.new_projeBase J ON J.new_projeId=B.new_KitapProjesi AND J.statecode=0 WHERE {ACTIVE}","book_id person_id publisher_id subbrand_id alternate_subbrand_id book_project_id project_name","book_id person_id",join_tables=8)
    add("CRM'de etkin kitaplara doğrudan kitap-sözleşme bağlantısıyla bağlı etkin sözleşmeleri çıkar. Her kitap-sözleşme çifti bir satır olsun. Kitap kimliği, ham adı, sözleşme kimliği ve ham numarasını book_id, book_name, contract_id, contract_number kolonlarında göster. Tarih önceliği, yürürlük veya hak sahipliği çıkarması yapma.","""SELECT DISTINCT B.new_kitapId book_id,B.new_name book_name,C.new_sozlesmeId contract_id,C.new_name contract_number
 FROM dbo.new_kitapBase B JOIN dbo.new_new_sozlesme_new_kitapBase L ON L.new_kitapid=B.new_kitapId
 JOIN dbo.new_sozlesmeBase C ON C.new_sozlesmeId=L.new_sozlesmeid AND C.statecode=0
 WHERE B.statecode=0 AND B.statuscode=1""","book_id book_name contract_id contract_number","book_id contract_id",join_tables=3)
    return out


def norm(value):
    if isinstance(value,UUID):return str(value).lower()
    if isinstance(value,str) and re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",value):return value.lower()
    if isinstance(value,(datetime,date)):return value.isoformat()
    return value


def compare_rows(case,expected,actual):
    errors=[]
    if len(expected)!=len(actual):errors.append("DATA: row count differs")
    def keyed(rows):
        result={}
        for row in rows:
            if set(row)!=set(case["columns"]):raise ValueError("Record column identity differs")
            key=tuple(norm(row[k]) for k in case["keys"])
            if key in result:raise ValueError("Duplicate declared row grain")
            result[key]=row
        return result
    try:
        left,right=keyed(expected),keyed(actual)
        if set(left)!=set(right):errors.append("DATA: row identities differ")
        for key in left.keys() & right.keys():
            for col in case["columns"]:
                a,b=norm(left[key][col]),norm(right[key][col])
                if col in case["numeric"]:
                    if a is None or b is None:
                        same=a is b
                    else:
                        same=not isinstance(b,(str,bool)) and Decimal(str(a))==Decimal(str(b))
                else:same=type(a) is type(b) and a==b
                if not same:errors.append("DATA: value differs "+col)
                if len(errors)>=30:return errors
    except (ValueError,TypeError,KeyError) as exc:errors.append("STRUCTURE: "+str(exc))
    return errors


def compare(case,answer,whole,records,expected_hash):
    errors=[];semantic=answer.get("semantic") or {}
    if semantic.get("engine")!="finance_contract_v1" or semantic.get("engineCodeHash")!=expected_hash:errors.append("STRUCTURE: engine/code hash mismatch")
    if answer.get("type")!="TEXT_TO_SQL":errors.append("STRUCTURE: complete answer not produced")
    if not answer.get("resultId") or whole.get("id")!=answer["resultId"]:errors.append("STRUCTURE: stored result identity differs")
    if whole.get("gaps") or semantic.get("gaps") or whole.get("sourceComplete") is not True:errors.append("STRUCTURE: source coverage incomplete")
    dataset=whole
    if whole.get("sections"):
        if len(whole["sections"])!=1:return errors+["STRUCTURE: unexpected multi-section output"]
        dataset=whole["sections"][0]
        if dataset.get("status")!="COMPLETE":errors.append("STRUCTURE: section incomplete")
        if answer.get("sections")!=whole["sections"]:errors.append("STRUCTURE: preview sections differ")
    rows=dataset.get("records");overview=whole.get("records")
    if not isinstance(rows,list) or not isinstance(overview,list):return errors+["STRUCTURE: stored records missing"]
    if whole.get("truncated") is not False or dataset.get("truncated") is not False:errors.append("STRUCTURE: truncated output")
    if dataset.get("totalRows")!=len(rows) or whole.get("totalRows")!=len(overview) or answer.get("rowCount")!=len(overview):errors.append("STRUCTURE: result cardinality metadata differs")
    names=[c.get("name") for c in dataset.get("columns",[])]
    if len(names)!=len(case["columns"]) or set(names)!=set(case["columns"]):errors.append("STRUCTURE: output column identities differ")
    if answer.get("records",[])!=overview[:len(answer.get("records",[]))] or answer.get("shownRows")!=len(answer.get("records",[])):errors.append("STRUCTURE: preview not prefix of same stored result")
    if dataset is not whole and overview!=[{"section":dataset.get("title"),"status":dataset.get("status"),"row_count":len(rows)}]:errors.append("STRUCTURE: section overview differs")
    errors.extend(compare_rows(case,records,rows))
    return errors


def reference(conn,case):
    return query(conn,case["referenceSql"])


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True);parser.add_argument("--only",default="")
    parser.add_argument("--base",default="http://127.0.0.1:8795")
    parser.add_argument("--as-of",required=True)
    args=parser.parse_args()
    if sys.platform!="linux" or not ROOT.is_dir() or not Path("/proc").is_dir():raise SystemExit("Remote connected test server only; local execution prohibited")
    if not re.fullmatch(r"http://127\.0\.0\.1:\d+",args.base):raise SystemExit("Use the actual loopback test API")
    require_reference_day(args.as_of)
    os.umask(0o077)
    lock=open("/tmp/finance-composable-live.lock","a")
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise SystemExit("Another finance acceptance run is active")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise SystemExit("Use an empty evidence directory")
    selected=[c for c in cases() if not args.only or c["id"] in args.only.split(",")]
    if not selected:raise SystemExit("No selected cases")
    before=manifest()
    expected_hash=hashlib.sha256(json.dumps({k.rsplit('/',1)[-1]:v for k,v in before.items() if '/finance_query/' in k},sort_keys=True).encode()).hexdigest()
    session=None;digest=None;conn=None;deleted=0;results=[];counts=Counter();finished={}
    def interrupt(signum,frame):raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM,interrupt)
    try:
        env=environment("nanobase-semantic-bridge");login=environment("timas-login")
        session=sqlite3.connect(login.get("SESSION_DB","/var/lib/timas-login/sessions.sqlite"))
        token=secrets.token_urlsafe(32);digest=hashlib.sha256(token.encode()).hexdigest()
        session.execute("INSERT INTO sessions(token,username,expires) VALUES(?,?,?)",(digest,"timasai",time.time()+900));session.commit()
        headers={"Content-Type":"application/json","X-Semantic-Caller":env.get("SEMANTIC_CALLER_TOKEN",""),"Cookie":("__Secure-timas_session" if login.get("COOKIE_SECURE","1")!="0" else "timas_session")+"="+token}
        def call(path,body=None):
            request=urllib.request.Request(args.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
            with urllib.request.urlopen(request,timeout=240) as response:return json.load(response)
        conn=connect("/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
        for case in selected:
            require_reference_day(args.as_of)
            if manifest()!=before:raise RuntimeError("Deployed code changed; stop before another question")
            item=dict(case,asOf=args.as_of,started=time.time());stop=False;retry_start=len(REFERENCE_RETRIES)
            try:
                session.execute("UPDATE sessions SET expires=? WHERE token=?",(time.time()+900,digest));session.commit()
                REFERENCE_CONTEXT.clear();REFERENCE_CONTEXT.update(caseId=case["id"],source="crm",phase="before_api")
                expected=reference(conn,case);item["reference"]=expected
                answer=call("/api/v1/ask",{"question":case["question"],"sampleSize":7});item["answer"]=answer
                whole=call("/api/v1/result/"+answer["resultId"]) if answer.get("resultId") else answer
                item["fullResult"]=whole
                errors=compare(case,answer,whole,expected,expected_hash);item["errors"]=errors
                item["status"]="FAIL" if errors else "FULL_ANSWER_PASS"
                require_reference_day(args.as_of)
                REFERENCE_CONTEXT["phase"]="after_api";after_ref=reference(conn,case);item["referenceAfter"]=after_ref
                changed=bool(compare_rows(case,expected,after_ref));item["referenceChanged"]=changed
                if changed:item["status"]="FAIL" if any(not e.startswith("DATA:") for e in errors) else "UNVERIFIED"
                if not expected and not errors:
                    item["status"]="UNVERIFIED";item["coverageGap"]="Empty source population does not exercise projection/join values"
                pair=case.get("paraphrase_of")
                if pair:
                    prior=finished.get(pair)
                    pair_status="UNVERIFIED";pair_errors=[]
                    if prior and prior.get("status")=="FULL_ANSWER_PASS" and item["status"]=="FULL_ANSWER_PASS":
                        if compare_rows(case,prior["referenceAfter"],expected):
                            pair_errors=["Source changed between paraphrases"]
                        else:
                            def data(result):return (result.get("sections") or [result])[0]["records"]
                            pair_errors=compare_rows(case,data(prior["fullResult"]),data(whole))
                            pair_status="FAIL" if pair_errors else "PASS"
                    item["paraphraseComparison"]={"other":pair,"status":pair_status,"errors":pair_errors}
                    if pair_status!="PASS" and item["status"]=="FULL_ANSWER_PASS":item["status"]="FAIL" if pair_status=="FAIL" else "UNVERIFIED"
                contrast=case.get("changed_from")
                if contrast:
                    prior=finished.get(contrast)
                    item["changedIntentComparison"]={"other":contrast,"referenceSqlDistinct":bool(prior and prior["referenceSql"]!=case["referenceSql"]),
                        "expectation":"Independent changed filter/period/group oracle; data values may coincide naturally"}
                    if prior and prior["referenceSql"]==case["referenceSql"]:raise ValueError("Changed intent reused identical oracle")
            except Exception as exc:
                structural=[e for e in item.get("errors",[]) if not e.startswith("DATA:")]
                item["status"]="FAIL" if structural else "UNVERIFIED"
                item["error"]=type(exc).__name__+": "+str(exc)[:500]
                stop=isinstance(exc,(TimeoutError,urllib.error.URLError))
            item["referenceRetries"]=REFERENCE_RETRIES[retry_start:]
            item["elapsedSeconds"]=round(time.time()-item["started"],2)
            save(out/(case["id"]+".json"),item);finished[case["id"]]=item
            counts[item["status"]]+=1
            results.append({k:item[k] for k in ("id","status","errors","error","elapsedSeconds","paraphraseComparison","changedIntentComparison") if k in item})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            if len(results)%10==0:print("BATCH",len(results),dict(counts),flush=True)
            if stop:print("STOP: API unavailable or request may still run; no duplicate workload",flush=True);break
    except BaseException as exc:
        counts["UNVERIFIED"]+=1;results.append(dict(id="ENVIRONMENT",status="UNVERIFIED",error=type(exc).__name__+": "+str(exc)[:400]))
    finally:
        if conn is not None:conn.close()
        if session is not None:
            try:
                if digest:deleted=session.execute("DELETE FROM sessions WHERE token=?",(digest,)).rowcount;session.commit()
            except Exception as exc:
                counts["UNVERIFIED"]+=1;results.append(dict(id="SESSION_CLEANUP",status="UNVERIFIED",error=str(exc)[:200]))
            finally:session.close()
        after=manifest()
        if before!=after:counts["UNVERIFIED"]+=1;results.append(dict(id="CODE_CHANGED",status="UNVERIFIED"))
        report=dict(asOf=args.as_of,api=args.base,source="connected real Timas_MSCRM",executionEnvironment="test server",planned=len(selected),completed=sum(r["id"].startswith("RL") for r in results),counts=dict(counts),results=results,sessionsDeleted=deleted,sourceWrites=0,codeBefore=before,codeAfter=after,codeStable=before==after,runnerSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),referenceRetries=REFERENCE_RETRIES,referenceRetryIsProductRecoveryEvidence=False,predefinedReportIdRequired=False)
        save(out/"report.json",report);print("FINAL",dict(counts),"sessionsDeleted",deleted,flush=True)
        fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
    return 1 if counts["FAIL"] or counts["UNVERIFIED"] or report["completed"]!=len(selected) else 0


if __name__=="__main__":raise SystemExit(main())
