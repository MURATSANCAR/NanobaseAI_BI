#!/usr/bin/env python3
"""CRM cover connector. Runs where the publisher's CRM is reachable (the editor's
GPU host is not on that network), for every book the editor has a card for.

  1. asks the editor which books need a CRM cover            GET  /catalog/cover-requests
  2. matches each book to the CRM book record: ISBN first (the ISBN in the card was
     verified verbatim on the book's imprint page), exact normalised title second;
     more than one match = AMBIGUOUS, nothing is guessed
  3. collects every image the CRM knows for that book with its date: the published
     cover (new_kitap.new_resimurl, dated by the record) and the cover alternatives
     of the book's project (new_kapakalternatifi.new_Link, dated by CreatedOn);
     the "none of these" placeholder is not an image of the book
  4. picks the NEWEST dated image (rule given by the user, 2026-09-20)
  5. fetches the file through a fetcher (the CRM stores paths, not bytes) and posts
     it to the editor                                           POST /catalog/covers

Read-only on the CRM. Configuration comes from the environment:
  EDITOR_API, EDITOR_MCP_KEY      editor endpoint + key
  CRM_CONNECTION_JSON             path of {host, port, user, password, database}
  CRM_IMAGE_ROOTS                 JSON: how a stored path becomes a readable location,
                                  e.g. {"resimurl": "/mnt/crm-web/kitap", "C:\\\\cube\\\\Timas_Folder_Entegrasyon": "/mnt/crm-cube"}
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path, PureWindowsPath

PLACEHOLDER = re.compile(r"^(hi[cç]biri|none|yok)$", re.I)


def norm_isbn(s: str | None) -> str:
    return re.sub(r"[^0-9Xx]", "", s or "").upper()


def norm_title(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", s or "").casefold().replace("ı", "i").replace("i̇", "i")
    return re.sub(r"[^a-z0-9çğıöşü]+", " ", s).strip()


def api(path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(os.environ["EDITOR_API"].rstrip("/") + path,
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"authorization": "Bearer " + os.environ["EDITOR_MCP_KEY"],
                                          "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def crm():
    import pymssql
    c = json.load(open(os.environ["CRM_CONNECTION_JSON"]))
    return pymssql.connect(server=c.get("host") or c.get("server"), port=int(c.get("port", 1433)),
                           user=c.get("user") or c.get("username"), password=c["password"],
                           database=c.get("database", "Timas_MSCRM"), login_timeout=20, timeout=120)


def find_book(cur, isbns: list[str], title: str) -> tuple[str, list[dict]]:
    for isbn in filter(None, map(norm_isbn, isbns)):
        cur.execute("SELECT new_kitapId, new_name, new_resimurl, new_projekarti, ModifiedOn FROM new_kitapBase"
                    " WHERE REPLACE(REPLACE(ISNULL(new_isbn13,''),'-',''),' ','')=%s OR"
                    " REPLACE(REPLACE(ISNULL(new_isbn,''),'-',''),' ','')=%s", (isbn, isbn))
        rows = cur.fetchall()
        if rows:
            return "ISBN", rows
    cur.execute("SELECT new_kitapId, new_name, new_resimurl, new_projekarti, ModifiedOn FROM new_kitapBase"
                " WHERE new_name LIKE %s", ("%" + title[:40].strip() + "%",))
    rows = [r for r in cur.fetchall() if norm_title(r["new_name"]) == norm_title(title)]
    return ("TITLE" if rows else "NONE"), rows


def candidates(cur, book: dict) -> list[dict]:
    out = []
    if book.get("new_resimurl"):
        out.append({"kind": "resimurl", "path": book["new_resimurl"], "name": "yayın kapağı",
                    "date": book["ModifiedOn"].isoformat()})
    if book.get("new_projekarti"):
        cur.execute("SELECT new_name, new_Link, CreatedOn FROM new_kapakalternatifiBase WHERE new_Proje=%s"
                    " AND statecode=0 AND new_Link IS NOT NULL", (str(book["new_projekarti"]),))
        for r in cur.fetchall():
            if not PLACEHOLDER.match((r["new_name"] or "").strip()):
                out.append({"kind": "kapak_alternatifi", "path": r["new_Link"], "name": r["new_name"],
                            "date": r["CreatedOn"].isoformat()})
    return sorted(out, key=lambda x: x["date"], reverse=True)       # newest first


def fetch(cand: dict) -> bytes | None:
    """Stored path -> bytes, through the configured roots (a mounted share or folder)."""
    roots = json.loads(os.environ.get("CRM_IMAGE_ROOTS", "{}"))
    p = cand["path"].replace("https://", "").replace("http://", "")
    if cand["kind"] == "resimurl" and "resimurl" in roots:
        f = Path(roots["resimurl"]) / Path(*PureWindowsPath(p).parts)
        return f.read_bytes() if f.is_file() else None
    for prefix, root in roots.items():
        if prefix != "resimurl" and p.lower().startswith(prefix.lower()):
            f = Path(root) / Path(*PureWindowsPath(p[len(prefix):].lstrip("\\/")).parts)
            return f.read_bytes() if f.is_file() else None
    return None


def main() -> int:
    import base64
    conn = crm()
    cur = conn.cursor(as_dict=True)
    done = 0
    for b in api("/catalog/cover-requests")["books"]:
        how, rows = find_book(cur, b["isbns"], b["title"])
        rep = {"book_id": b["book_id"], "matched_by": how, "candidates": [], "outcome": "NO_MATCH"}
        if len(rows) > 1:
            rep.update(outcome="AMBIGUOUS", detail=f"{len(rows)} CRM kaydı: " + "; ".join(r["new_name"] for r in rows[:5]))
        elif rows:
            book = rows[0]
            cands = candidates(cur, book)
            rep.update(crm_book_id=str(book["new_kitapId"]), crm_title=book["new_name"], candidates=cands,
                       outcome="NO_IMAGE" if not cands else "FETCH_FAILED")
            for cand in cands:                      # newest first; an unreadable file falls to the next
                data = fetch(cand)
                if data:
                    rep.update(outcome="STORED", chosen=cand, file_name=PureWindowsPath(cand["path"]).name,
                               image_b64=base64.b64encode(data).decode())
                    break
        print(b["title"], "→", rep["outcome"], (rep.get("chosen") or {}).get("name", ""), flush=True)
        api("/catalog/covers", rep)
        done += rep["outcome"] == "STORED"
    return 0 if done or True else 1


if __name__ == "__main__":
    sys.exit(main())
