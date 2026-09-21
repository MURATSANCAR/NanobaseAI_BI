"""Server-only, real Editor API vs independent raw DB and original PDF checks.
No local tests, fixture records, model calls, writes or index rebuilds.
"""
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

import pymupdf
from editor import db
from editor.config import settings

TARGETS = {"anne-terligi": [20,49], "levent-dunya-harikalarinin-pesinde": [6,10],
           "dunyanin-en-korkak-hayvani": [5,6]}


def request(path):
    req = urllib.request.Request("http://127.0.0.1:8000"+path,
        headers={"Authorization":"Bearer "+settings().gateway_internal_key})
    with urllib.request.urlopen(req,timeout=120) as response:
        assert response.status==200
        return json.load(response)


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def compact(value):
    return re.sub(r"\s+", "", re.sub(r"(?<=\w)[-\u00ad]\s*\n\s*(?=[a-zçğıöşü])", "", value))


def table_state(c):
    result = {}
    for name in ("claim","event","emotion","report","generation","evidence","page_text",
                 "paragraph","page_role","model_call","analysis_job"):
        # Full row multiset: independent of primary-key shape and table ordering.
        result[name] = dict(c.execute(f"SELECT count(*) AS count, "
            f"md5(string_agg(row_hash, '' ORDER BY row_hash)) AS md5 FROM "
            f"(SELECT md5(to_jsonb(t)::text) AS row_hash FROM ed.{name} t) h").fetchone())
    return result


def main():
    health=request("/health")
    assert health["maintenance"] is True
    results=[]
    total=0
    with db.tx() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        c.execute("SET LOCAL statement_timeout='30s'")
        before=table_state(c)
        gens=c.execute("SELECT DISTINCT ON (g.book_version_id) g.id,b.title,bv.file_path,bv.sha256 "
            "FROM ed.generation g JOIN ed.book_version bv ON bv.id=g.book_version_id "
            "JOIN ed.book b ON b.id=bv.book_id WHERE g.sealed_at IS NOT NULL "
            "ORDER BY g.book_version_id,g.sealed_at DESC").fetchall()
        for gen in gens:
            gid=str(gen["id"])
            base=f"/v1/generations/{gid}/source"
            manifest=[r["page_no"] for r in c.execute("SELECT p.page_no FROM ed.page p JOIN "
                "ed.generation g ON g.book_version_id=p.book_version_id WHERE g.id=%s ORDER BY p.page_no",(gid,))]
            raw={(r["page_no"],r["source"]):r["text"] for r in c.execute(
                "SELECT page_no,source,text FROM ed.page_text WHERE generation_id=%s",(gid,))}
            cov=request(base+"/coverage")
            plan=request(base+"/plan")
            assert cov["included_pages"]==manifest and cov["excluded_pages"]==[]
            assert cov["physical_pages"]==len(manifest) and cov["complete_book"] is False
            assert [p for a,b in plan["text_chunks"] for p in range(a,b+1)]==manifest
            assert [p for ch in plan["chapters"] for p in range(ch["page_from"],ch["page_to"]+1)]==manifest
            ps=request(base+"/passages")
            assert ps["indexed"] is False
            passages=ps["passages"]
            assert len({p["source_span"]["span_id"] for p in passages})==len(passages)
            target_results=[]
            digests=[]
            original=Path(gen["file_path"])
            assert hashlib.sha256(original.read_bytes()).hexdigest()==gen["sha256"]
            with pymupdf.open(original) as pdf:
                assert len(pdf)==len(manifest)
                for page_no in manifest:
                    page=request(base+f"/pages/{page_no}")
                    assert page["generation_id"]==gid and page["page_no"]==page_no
                    assert page["semantic_acceptance"] is False and page["included_in_extraction"] is True
                    spans=page["spans"]+page["alternatives"]
                    # Every original non-space character has exactly one retained
                    # representation: reading span OR explicit alternative.
                    for kind in ("TEXT_LAYER","OCR"):
                        text=raw.get((page_no,kind),"")
                        seen=set()
                        for span in [s for s in spans if s["source"]==kind]:
                            a,b=span["start"],span["end"]
                            assert 0<=a<b<=len(text)
                            assert span["text"]==text[a:b] and span["source_sha256"]==sha(text)
                            identity=f"{page['policy']}:{gid}:{page_no}:{kind}:{sha(text)}:{a}:{b}"
                            assert span["span_id"]==sha(identity)
                            chars={i for i in range(a,b) if not text[i].isspace()}
                            assert not (chars & seen), (gid,page_no,kind,"duplicate source characters")
                            seen |= chars
                        assert seen=={i for i,ch in enumerate(text) if not ch.isspace()}, (gid,page_no,kind,"lost text")
                    indexed=[p for p in passages if p["page_no"]==page_no]
                    assert [p["text"] for p in indexed]==[s["text"] for s in page["spans"]]
                    assert [p["source_span"]["span_id"] for p in indexed]==[s["span_id"] for s in page["spans"]]
                    assert all(p["reading_sha256"]==page["reading_sha256"] for p in indexed)
                    assert all(s["text"] in page["numbered_text"] for s in page["spans"])
                    if page_no in TARGETS.get(gen["title"],[]):
                        pdf_text=compact(pdf[page_no-1].get_text())
                        layer=[s for s in page["spans"] if s["source"]=="TEXT_LAYER"]
                        assert layer and all(compact(s["text"]) in pdf_text for s in layer), (gen["title"],page_no,"original PDF mismatch")
                        body=max(layer,key=lambda s:len(s["text"]))
                        quote=body["text"][:500]
                        check=request(base+"/quote-check?"+urllib.parse.urlencode(
                            {"page_no":page_no,"paragraph":body["idx"],"quote":quote}))
                        assert check["verified"] and check["span_ids"]==[body["span_id"]]
                        # The same real excerpt with another real paragraph reference
                        # must not pass: no synthetic source data is introduced.
                        other=next((s for s in layer if s["idx"]!=body["idx"] and quote not in s["text"]),None)
                        wrong=None
                        if other:
                            wrong=request(base+"/quote-check?"+urllib.parse.urlencode(
                                {"page_no":page_no,"paragraph":other["idx"],"quote":quote}))
                            assert wrong["verified"] is False
                        target_results.append({"page":page_no,"pdf_match":True,"quote_verified":True,
                            "wrong_real_paragraph_rejected":wrong is not None,"span_id":body["span_id"]})
                    if gen["title"]=="dunyanin-en-korkak-hayvani" and page_no==5:
                        assert page["spans"][0]["text"]=="MERAKLI VOMBAT" and page["spans"][0]["role"]=="heading"
                        assert any(ch["page_from"]==5 for ch in plan["chapters"])
                    digests.append(page["reading_sha256"])
                    total+=1
                    if total%10==0:
                        print(json.dumps({"pages_checked":total,"passed":total,"failed":0}),flush=True)
            results.append({"generation_id":gid,"title":gen["title"],"status":"PASSED",
                "physical_pages":len(manifest),"reading_sha256":sha("".join(digests)),
                "source_passages":len(passages),"source_issue_pages":len(cov["unresolved_pages"]),
                "unclassified_pages":len(cov["classification_unresolved_pages"]),
                "targets":target_results,"semantic_acceptance":False})
    # A separate snapshot detects unexpected concurrent changes during validation.
    with db.tx() as c:
        c.execute("SET TRANSACTION READ ONLY")
        after=table_state(c)
    assert before==after, "source/analysis tables changed during read-only validation"
    result={"code_version":os.environ.get("EDITOR_CODE_VERSION"),
        "api":"tt-gpu/editor-control:8000","database":"tt-gpu/editor-postgres/editor/ed",
        "real_books":len(gens),"pages_checked":total,"results":results,"table_state":after,
        "original_tables_unchanged":True,"maintenance":True,
        "scope":"source retention, physical coverage, real quote references, original PDF targets",
        "not_verified":["semantic page classification","OCR conflict resolution and reading order",
            "new-generation evidence persistence","Qdrant rebuild and search","full-book semantic acceptance"]}
    Path("/tmp/source-verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
