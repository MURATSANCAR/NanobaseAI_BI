"""Operator/editor CLI (runs inside editor-mcp via `editorctl`).

  python -m editor.cli analyze <file.pdf> [--title T] [--universe U] [--age A]
  python -m editor.cli queue [--force] [--code-version]
  python -m editor.cli status <job_id>
  python -m editor.cli wait <job_id>
  python -m editor.cli report <generation_id>
  python -m editor.cli readiness <generation_id>
  python -m editor.cli accept <generation_id> --editor NAME [--note N] [--waive BLOCKER ...]
  python -m editor.cli review list <generation_id>
  python -m editor.cli review decide <item_id> approve|reject|correct --editor NAME [--json '{...}']
  python -m editor.cli canon add <universe> <kind> <key> '<json>' --editor NAME [--claim ID]

Editor decisions (and canon writes) exist only here, not as Hermes tools.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

from . import catalog, db, document, jobs


def _print(x) -> None:
    print(json.dumps(x, ensure_ascii=False, indent=1, default=str))


def queue_all(force: bool, code_version: bool) -> dict:
    """Analyse every book in the inbox, one after another. The models are shared, so two
    analyses at once would take the GPU from each other; a book already analysed is skipped
    (--force runs it again, --code-version only when the sealed run is from older code)."""
    from .workflow.activities import _code_version
    version = _code_version()
    out = []
    for item in document.list_inbox():
        info = document.inspect_book(item["file_name"])
        sealed = db.one("SELECT id, code_version FROM generation WHERE book_version_id=%s AND"
                        " sealed_at IS NOT NULL ORDER BY created_at DESC LIMIT 1",
                        info["book_version_id"])
        if sealed and not force and not (code_version and sealed["code_version"] != version):
            out.append({"file": item["file_name"], "skipped": f"mühürlü nesil var: {sealed['id']}"})
            print(f"{time.strftime('%H:%M:%S')} ATLA {item['file_name']} ({out[-1]['skipped']})", flush=True)
            continue
        job = asyncio.run(jobs.start_analysis_job(item["file_name"], requested_by="editorctl queue"))
        print(f"{time.strftime('%H:%M:%S')} BAŞLADI {item['file_name']} → {job['job_id']}", flush=True)
        last = None
        while True:
            st = jobs.get_job_status(job["job_id"])
            if st["step"] != last:
                print(f"  {time.strftime('%H:%M:%S')} {st['status']} {st['step']}", flush=True)
                last = st["step"]
            if st["status"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
                break
            time.sleep(20)
        out.append({"file": item["file_name"], "job_id": job["job_id"], "status": st["status"],
                    "error": st.get("error")})
        print(f"{time.strftime('%H:%M:%S')} BİTTİ {item['file_name']}: {st['status']} {st.get('error') or ''}",
              flush=True)
    return {"books": out}


def decide(item_id: str, decision: str, editor: str, data: dict | None) -> dict:
    status = {"approve": "APPROVED", "reject": "REJECTED", "correct": "CORRECTED"}[decision]
    claim_status = {"approve": "EDITOR_APPROVED", "reject": "EDITOR_REJECTED",
                    "correct": "EDITOR_CORRECTED"}[decision]
    with db.tx() as c:
        it = c.execute("SELECT r.*, bv.book_id FROM review_item r JOIN generation g ON g.id=r.generation_id"
                       " JOIN book_version bv ON bv.id=g.book_version_id WHERE r.id=%s", (item_id,)).fetchone()
        if it is None:
            raise SystemExit(f"review item {item_id} not found")
        if it["status"] != "OPEN":
            raise SystemExit(f"already decided: {it['status']}")
        if decision == "correct" and not data:
            raise SystemExit("--json correction is required for 'correct'")
        c.execute("UPDATE review_item SET status=%s, decided_by=%s, decision=%s, decided_at=now() WHERE id=%s",
                  (status, editor, db.J(data or {}), item_id))
        if it["claim_id"]:
            c.execute("UPDATE claim SET status=%s WHERE id=%s", (claim_status, it["claim_id"]))
        if it["contradiction_id"]:
            c.execute("UPDATE contradiction SET status=%s WHERE id=%s",
                      ("EDITOR_DISMISSED" if decision == "reject" else "EDITOR_CONFIRMED",
                       it["contradiction_id"]))
        if decision == "correct":
            cl = c.execute("SELECT kind, subject, claim FROM claim WHERE id=%s", (it["claim_id"],)).fetchone() \
                if it["claim_id"] else None
            c.execute("INSERT INTO editor_correction(book_id, review_item_id, target_kind, target_key,"
                      " correction, editor) VALUES (%s,%s,%s,%s,%s,%s)",
                      (it["book_id"], item_id, data.get("target_kind") or (cl or {}).get("kind", "CLAIM"),
                       data.get("target_key") or (cl or {}).get("subject") or (cl or {}).get("claim", "")[:200],
                       db.J(data), editor))
    return {"item": item_id, "status": status}


def canon_add(universe: str, kind: str, key: str, value: dict, editor: str, claim: str | None) -> dict:
    with db.tx() as c:
        old = c.execute("SELECT id FROM canon_entry WHERE universe=%s AND kind=%s AND key=%s AND"
                        " superseded_by IS NULL", (universe, kind, key)).fetchone()
        row = c.execute("INSERT INTO canon_entry(universe, kind, key, value, source_claim, approved_by)"
                        " VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                        (universe, kind, key, db.J(value), claim, editor)).fetchone()
        if old:
            c.execute("UPDATE canon_entry SET superseded_by=%s WHERE id=%s", (row["id"], old["id"]))
    return {"canon_id": str(row["id"]), "superseded": str(old["id"]) if old else None}


def main() -> None:
    p = argparse.ArgumentParser(prog="editor")
    sp = p.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("analyze")
    a.add_argument("file")
    a.add_argument("--title")
    a.add_argument("--universe")
    a.add_argument("--age")
    q = sp.add_parser("queue")
    q.add_argument("--force", action="store_true")
    q.add_argument("--code-version", action="store_true")
    sp.add_parser("status").add_argument("job_id")
    sp.add_parser("wait").add_argument("job_id")
    sp.add_parser("report").add_argument("generation_id")
    r = sp.add_parser("review")
    rs = r.add_subparsers(dest="rcmd", required=True)
    rs.add_parser("list").add_argument("generation_id")
    d = rs.add_parser("decide")
    d.add_argument("item_id")
    d.add_argument("decision", choices=["approve", "reject", "correct"])
    d.add_argument("--editor", required=True)
    d.add_argument("--json")
    c = sp.add_parser("canon")
    cs = c.add_subparsers(dest="ccmd", required=True)
    ca = cs.add_parser("add")
    for x in ("universe", "kind", "key", "value"):
        ca.add_argument(x)
    ca.add_argument("--editor", required=True)
    ca.add_argument("--claim")
    sp.add_parser("migrate")
    ac = sp.add_parser("accept")
    ac.add_argument("generation_id")
    ac.add_argument("--editor", required=True)
    ac.add_argument("--note", default="")
    ac.add_argument("--waive", nargs="*", default=[])
    sp.add_parser("readiness").add_argument("generation_id")
    cat = sp.add_parser("catalog")
    cats = cat.add_subparsers(dest="catcmd", required=True)
    cats.add_parser("rebuild")
    cq = cats.add_parser("search")
    cq.add_argument("query")
    cq.add_argument("--age", type=int)
    cats.add_parser("card").add_argument("book_id")
    cats.add_parser("web-cover").add_argument("book_id")
    cv = sp.add_parser("cover")
    cv.add_argument("book_id")
    cv.add_argument("file_name")
    cv.add_argument("--by", required=True)
    args = p.parse_args()

    if args.cmd == "analyze":
        _print(asyncio.run(jobs.start_analysis_job(args.file, args.title, args.universe, args.age,
                                                   requested_by="editorctl")))
    elif args.cmd == "queue":
        _print(queue_all(args.force, args.code_version))
    elif args.cmd == "status":
        _print(jobs.get_job_status(args.job_id))
    elif args.cmd == "wait":
        last = None
        while True:
            s = jobs.get_job_status(args.job_id)
            if s["step"] != last:
                print(time.strftime("%H:%M:%S"), s["status"], s["step"], flush=True)
                last = s["step"]
            if s["status"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
                _print(s)
                sys.exit(0 if s["status"] == "SUCCEEDED" else 1)
            time.sleep(15)
    elif args.cmd == "report":
        rep = jobs.get_report(args.generation_id)
        print(rep["markdown"] if rep else "no report")
    elif args.cmd == "review" and args.rcmd == "list":
        _print(jobs.list_review_queue(args.generation_id, "OPEN", 500))
    elif args.cmd == "review" and args.rcmd == "decide":
        _print(decide(args.item_id, args.decision, args.editor, json.loads(args.json) if args.json else None))
    elif args.cmd == "canon":
        _print(canon_add(args.universe, args.kind, args.key, json.loads(args.value), args.editor, args.claim))
    elif args.cmd == "catalog" and args.catcmd == "rebuild":
        _print(asyncio.run(catalog.rebuild_all()))
    elif args.cmd == "catalog" and args.catcmd == "search":
        _print(asyncio.run(catalog.search_books(args.query, 5, args.age)))
    elif args.cmd == "catalog" and args.catcmd == "card":
        _print(catalog.get_book_card(args.book_id))
    elif args.cmd == "catalog" and args.catcmd == "web-cover":
        from . import web_cover
        _print(asyncio.run(web_cover.sync_book(args.book_id)))
    elif args.cmd == "cover":
        _print(catalog.set_uploaded_cover(args.book_id, args.file_name, args.by))
    elif args.cmd == "accept":
        from . import foundation
        _print(foundation.accept(args.generation_id, args.editor, args.note, args.waive))
    elif args.cmd == "readiness":
        from . import foundation
        _print(foundation.readiness(args.generation_id))
    elif args.cmd == "migrate":
        _print(db.migrate())


if __name__ == "__main__":
    main()
