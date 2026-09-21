"""Run ONLY inside editor-control on tt-gpu: real API vs independent live DB.

Read-only, no model calls, no fixtures, no mutation/retry simulations. Checks
complete paginated values, rejection filtering and readiness on six real books.
"""
import datetime
import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid

from editor import db
from editor.config import settings


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [normalized(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime.datetime,datetime.date)):
        return value.isoformat()
    return value


def request(path, authenticated=True):
    headers = {"Authorization": "Bearer " + settings().gateway_internal_key} if authenticated else {}
    req = urllib.request.Request("http://127.0.0.1:8000" + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status,json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code,None


def oracle(c, gid):
    # Derive eligibility from original tables in Python, never from usable_* views.
    claims = c.execute("SELECT * FROM ed.claim WHERE generation_id=%s", (gid,)).fetchall()
    evidence = {r["id"]:r for r in c.execute("SELECT * FROM ed.evidence WHERE generation_id=%s", (gid,))}
    regions = {r["id"] for r in c.execute("SELECT id FROM ed.visual_region WHERE generation_id=%s", (gid,))}
    pages = {r["page_no"] for r in c.execute("SELECT p.page_no FROM ed.page p JOIN ed.generation g "
        "ON g.book_version_id=p.book_version_id WHERE g.id=%s", (gid,))}
    links = {}
    for r in c.execute("SELECT ce.* FROM ed.claim_evidence ce JOIN ed.claim cl ON cl.id=ce.claim_id "
                       "WHERE cl.generation_id=%s", (gid,)):
        links.setdefault(r["claim_id"],[]).append(r["evidence_id"])
    eligible = {}
    for cl in claims:
        if cl["status"] not in {"VERIFIED","EDITOR_APPROVED","EDITOR_CORRECTED"} or cl["needs_editor_review"]:
            continue
        if not set(cl["source_pages"]) <= pages:
            continue
        evs = [evidence.get(eid) for eid in links.get(cl["id"],[])]
        if not evs or any(e is None or e["page_no"] not in pages for e in evs):
            continue
        if any(e["quote_verified"] or (e["kind"]=="VISUAL" and e["region_id"] in regions) for e in evs):
            eligible[cl["id"]] = cl
    events = []
    for event in c.execute("SELECT * FROM ed.event WHERE generation_id=%s", (gid,)):
        cl=eligible.get(event["claim_id"])
        if cl and event["merged_into"] is None and event["summary"]==cl["claim"]:
            events.append(event)
    characters = {r["id"] for r in c.execute("SELECT id FROM ed.character WHERE generation_id=%s", (gid,))}
    emotions = []
    for emotion in c.execute("SELECT * FROM ed.emotion WHERE generation_id=%s", (gid,)):
        cl=eligible.get(emotion["claim_id"])
        if not cl or emotion["character_id"] not in characters:
            continue
        payload=cl["payload"]
        if ("supersedes" not in payload and payload.get("emotion")==emotion["emotion"]
                and (payload.get("trigger") or "")== (emotion["trigger"] or "")):
            emotions.append(emotion)
    return {"claims":list(eligible.values()),"events":events,"emotions":emotions}


def main():
    results=[]
    status,health=request("/health")
    assert status==200 and health["maintenance"] is True, health
    assert request("/health",False)[0]==401
    assert request("/v1/generations/not-a-uuid/readiness")[0]==422
    assert request("/v1/generations/00000000-0000-0000-0000-000000000000/readiness")[0]==404
    with db.tx() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        c.execute("SET LOCAL statement_timeout='20s'")
        gens=c.execute("SELECT DISTINCT ON (book_version_id) id,book_version_id FROM ed.generation "
            "WHERE sealed_at IS NOT NULL ORDER BY book_version_id,sealed_at DESC").fetchall()
        for gen in gens:
            gid=str(gen["id"])
            expected=oracle(c,gen["id"])
            status,ready=request(f"/v1/generations/{gid}/readiness")
            assert status==200 and ready["accepted"] is False and ready["complete_book"] is False
            assert "LEGACY_UNASSESSED" in ready["blockers"]
            for kind,rows in expected.items():
                result=[]
                offset=0
                while True:
                    # Start with 1 to exercise real preview truncation, then read all values.
                    limit=1 if offset==0 else 100
                    status,page=request(f"/v1/generations/{gid}/records/{kind}?limit={limit}&offset={offset}")
                    assert status==200 and page["total"]==len(rows), (gid,kind,status)
                    result+=page["records"]
                    offset+=len(page["records"])
                    assert page["truncated"] == (offset<len(rows)), (gid,kind,"truncation")
                    if not page["truncated"]:
                        break
                    assert page["records"], "pagination made no progress"
                reference=normalized(sorted(rows,key=lambda r:str(r["id"])))
                assert result==reference, (gid,kind,"full values mismatch")
                results.append({"generation_id":gid,"kind":kind,"count":len(result),"status":"PASSED",
                    "sha256":hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
                if len(results)%10==0:
                    print(json.dumps({"progress":len(results),"passed":len(results),"failed":0,"unverified":0}),flush=True)
    print(json.dumps({"code_version":os.environ.get("EDITOR_CODE_VERSION"),"api":"editor-control:8000",
        "database":"tt-gpu/editor-postgres/editor/ed","real_books":len(gens),"results":results,
        "maintenance":True,"auth_validation":"PASSED","scope":"read-only foundation API",
        "not_verified":["automatic rebuild","crash-retry persistence","new-generation semantic acceptance"]},ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
