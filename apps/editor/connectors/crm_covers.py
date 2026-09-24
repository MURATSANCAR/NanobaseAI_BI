#!/usr/bin/env python3
"""CRM connector (cover + publisher record). Runs where the publisher's CRM is reachable
(the editor's GPU host is not on that network), for every book the editor knows.

  1. asks the editor for its books (title, verified ISBNs, verified authors)
                                                               GET  /catalog/cover-requests
  2. reads the CRM book list ONCE (new_kitapBase, ~14k rows) and matches each book:
       ISBN      the ISBN in the card was verified verbatim on the book's imprint page
       TITLE     folded title equal to the CRM name / book name / product name
                 (folding: Turkish letters to ASCII, punctuation and dashes to spaces, so a
                 file-name title like «anne-terligi» equals «Anne Terliği»)
       PARTIAL   only when nothing is equal: the editor title's words (at least two) open
                 the CRM title word by word, each word a prefix («kaybolan balinalar» →
                 «Kaybolan Balinaların Şarkısı»)
     several records left → the editor's verified author narrows them; records that still
     share one folded title (a trailing «(Önceki Ebat)»-like note aside) and one author (an
     empty author field aside) are editions of one book (matched_by gets
     «+EDITIONS»): the record carrying a project card, else the newest, gives the text, and
     cover images are collected from all of them. Different titles left = AMBIGUOUS,
     nothing is guessed.
  3. publisher record for the card: authors (new_yazartext, else the «Yazar - …» participation
     rows, else the project's probable author), illustrators (new_cizerlertext), summary
     (web text > new_ozet > old summary > the project's one-sentence idea), ISBN, stock code,
     first publication date, and the publisher's classification of the book — target audience
     (new_hedefkitle), genres (new_turlertext), web categories, target age range, page count —
     which decides what the editor reads the book as (editor.book_type)
  4. every image the CRM knows for the book with its date: the published cover
     (new_kitap.new_resimurl, dated by the record) and the cover alternatives of the book's
     project (new_kapakalternatifi.new_Link, dated by CreatedOn); the NEWEST readable one wins
     (rule given by the user, 2026-09-20). The CRM stores paths, not bytes → CRM_IMAGE_ROOTS.
  5. posts the result, with or without an image                POST /catalog/covers

Read-only on the CRM. Configuration comes from the environment:
  EDITOR_API, EDITOR_MCP_KEY      editor endpoint + key
  CRM_CONNECTION_JSON             path of {host, port, user, password, database}
  CRM_IMAGE_ROOTS                 JSON: how a stored path becomes a readable location,
                                  e.g. {"resimurl": "/mnt/crm-web/kitap", "C:\\\\cube\\\\Timas_Folder_Entegrasyon": "/mnt/crm-cube"}

`--dry-run TITLE...` matches the given titles against the CRM and prints what would be
posted, without calling the editor.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path, PureWindowsPath

PLACEHOLDER = re.compile(r"^(hi[cç]biri|none|yok)$", re.I)
ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")
SUMMARY_FIELDS = ("new_kitaptanitimwebmetni", "new_ozet", "new_kitabineskiozeti")
AUDIENCE = {1: "CHILD", 2: "YOUNG", 3: "ADULT"}         # new_hedefkitle picklist


def norm_isbn(s: str | None) -> str:
    return re.sub(r"[^0-9Xx]", "", s or "").upper()


def fold(s: str | None) -> str:
    s = unicodedata.normalize("NFKC", s or "").casefold().translate(ASCII)
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def plain(s: str | None) -> str:
    """CRM rich-text fields hold HTML (<p>, &uuml;); the card shows plain paragraphs."""
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|li)>", "\n", s or "")
    s = html.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ")
    return "\n".join(x for x in (re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines()) if x)


def names(s: str | None) -> list[str]:
    return [x.strip() for x in re.split(r"\s*[,;/&]\s*|\s+ve\s+", s or "") if x.strip()]


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
                           database=c.get("database", "Timas_MSCRM"), login_timeout=20, timeout=300)


def load_books(cur) -> list[dict]:
    cur.execute("SELECT new_kitapId, new_name, new_KitabnAd, new_urunadi, new_isbn, new_isbn13, new_resimurl,"
                " new_projekarti, new_yazartext, new_cizerlertext, new_StokKodu, new_ilkyayintarihi,"
                " new_hedefkitle, new_turlertext, new_webkategorileritext, new_hedefkitleyasbaslangic,"
                " new_hedefkitleyasbitis, new_sayfasayisi, ModifiedOn, " + ", ".join(f"CAST({f} AS nvarchar(max)) AS {f}" for f in SUMMARY_FIELDS) +
                " FROM new_kitapBase WHERE statecode=0")
    books = cur.fetchall()
    for b in books:
        b["_titles"] = {t for t in (fold(b.get(k)) for k in ("new_name", "new_KitabnAd", "new_urunadi")) if t}
        b["_isbns"] = {i for i in (norm_isbn(b.get("new_isbn13")), norm_isbn(b.get("new_isbn"))) if i}
    return books


def _opens(words: list[str], title: str) -> bool:
    other = title.split()
    return len(words) >= 2 and len(other) >= len(words) and all(o.startswith(w) for w, o in zip(words, other))


def _author_hit(authors: list[str], book: dict) -> bool:
    have = fold(book.get("new_yazartext"))
    return any(fold(a) and fold(a) in have for a in authors)


def match(books: list[dict], isbns: list[str], title: str, authors: list[str] = ()) -> tuple[str, list[dict], str]:
    """-> (matched_by, records, detail). One record, or several editions of one book."""
    wanted = {i for i in map(norm_isbn, isbns) if i}
    how, rows = "NONE", []
    if wanted:
        how, rows = "ISBN", [b for b in books if b["_isbns"] & wanted]
    if not rows:
        t = fold(title)
        how, rows = "TITLE", [b for b in books if t and t in b["_titles"]]
    if not rows:
        words = fold(title).split()
        how, rows = "PARTIAL", [b for b in books if any(_opens(words, x) for x in b["_titles"])]
    if not rows:
        return "NONE", [], ""
    if len(rows) > 1 and authors:
        rows = [b for b in rows if _author_hit(authors, b)] or rows
    if len(rows) == 1:
        return how, rows, ""
    # «X (Önceki Ebat)», «X?» and a record whose author was left empty are still book X.
    same_title = len({fold(re.sub(r"\s*\([^)]*\)\s*$", "", b["new_name"])) for b in rows}) == 1
    same_author = len({a for a in (fold(b.get("new_yazartext")) for b in rows) if a}) <= 1
    if same_title and same_author:
        rows.sort(key=lambda b: (b["new_projekarti"] is not None, b["ModifiedOn"]), reverse=True)
        return how + "+EDITIONS", rows, f"{len(rows)} baskı: " + "; ".join(
            filter(None, (b.get("new_isbn13") or b.get("new_isbn") for b in rows)))
    return "AMBIGUOUS", rows, f"{len(rows)} CRM kaydı: " + "; ".join(b["new_name"] for b in rows[:5])


def project(cur, project_id) -> dict:
    if not project_id:
        return {}
    cur.execute("SELECT new_name, new_ProjeFikriTekcmleile, new_olasiyazartext FROM new_projeBase"
                " WHERE new_projeId=%s", (str(project_id),))
    return cur.fetchone() or {}


def participants(cur, book_id, role: str) -> list[str]:
    cur.execute("SELECT new_name FROM new_eserkatilimBase WHERE new_Kitap=%s AND statecode=0"
                " AND new_name LIKE %s ORDER BY CreatedOn", (str(book_id), role + " - %"))
    return [r["new_name"].split(" - ", 1)[1].strip() for r in cur.fetchall()]


def genres(s: str | None) -> list[str]:
    """new_turlertext: «Bilim Tarihi,İnceleme-Araştırma» — comma separated, kept as written."""
    return list(dict.fromkeys(x.strip() for x in (s or "").split(",") if x.strip()))


def age(v) -> int | None:
    """A target age of 0 is an unfilled field, not a newborn reader."""
    return int(v) if v not in (None, "") and int(v) > 0 else None


def record(cur, book: dict) -> dict:
    """The publisher's facts about the book, as the CRM holds them (not verified in the book)."""
    proj = project(cur, book.get("new_projekarti"))
    authors = names(book.get("new_yazartext")) or participants(cur, book["new_kitapId"], "Yazar") \
        or names(proj.get("new_olasiyazartext"))
    summary, field = next(((plain(book[f]), f) for f in SUMMARY_FIELDS if plain(book.get(f))),
                          (plain(proj.get("new_ProjeFikriTekcmleile")), "new_proje.new_ProjeFikriTekcmleile"))
    first = book.get("new_ilkyayintarihi")
    return {"crm_book_id": str(book["new_kitapId"]), "crm_project_id": str(book["new_projekarti"] or "") or None,
            "title": book["new_name"], "authors": authors, "illustrators": names(book.get("new_cizerlertext")),
            "summary": summary or None, "summary_field": field if summary else None,
            "isbn": book.get("new_isbn13") or book.get("new_isbn"), "stock_code": book.get("new_StokKodu"),
            "first_publish_date": first.date().isoformat() if first else None,
            "audience": AUDIENCE.get(book.get("new_hedefkitle")), "genres": genres(book.get("new_turlertext")),
            "web_categories": (book.get("new_webkategorileritext") or "").strip() or None,
            "age_from": age(book.get("new_hedefkitleyasbaslangic")), "age_to": age(book.get("new_hedefkitleyasbitis")),
            "page_count": age(book.get("new_sayfasayisi")),
            "crm_modified_on": book["ModifiedOn"].isoformat()}


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
    return out


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


def report(cur, books: list[dict], b: dict, with_image: bool = True) -> dict:
    import base64
    how, rows, detail = match(books, b.get("isbns") or [], b["title"], b.get("authors") or [])
    rep = {"book_id": b.get("book_id"), "matched_by": how, "candidates": [], "outcome": "NO_MATCH",
           "detail": detail or None}
    if how == "AMBIGUOUS":
        rep["outcome"] = "AMBIGUOUS"
    elif rows:
        main_row = rows[0]
        cands = sorted((c for r in rows for c in candidates(cur, r)), key=lambda x: x["date"], reverse=True)
        rep.update(crm_book_id=str(main_row["new_kitapId"]), crm_title=main_row["new_name"], candidates=cands,
                   crm=record(cur, main_row), outcome="NO_IMAGE" if not cands else "FETCH_FAILED")
        for cand in cands if with_image else []:     # newest first; an unreadable file falls to the next
            data = fetch(cand)
            if data:
                rep.update(outcome="STORED", chosen=cand, file_name=PureWindowsPath(cand["path"]).name,
                           image_b64=base64.b64encode(data).decode())
                break
    return rep


def main(argv: list[str]) -> int:
    conn = crm()
    cur = conn.cursor(as_dict=True)
    books = load_books(cur)
    if argv[:1] == ["--dry-run"]:
        for t in argv[1:]:
            rep = report(cur, books, {"title": t}, with_image=False)
            crm_rec = rep.get("crm") or {}
            print(json.dumps({"title": t, "matched_by": rep["matched_by"], "outcome": rep["outcome"],
                              "crm_title": rep.get("crm_title"), "detail": rep["detail"],
                              "authors": crm_rec.get("authors"), "summary_field": crm_rec.get("summary_field"),
                              "summary": (crm_rec.get("summary") or "")[:80], "images": len(rep["candidates"])},
                             ensure_ascii=False), flush=True)
        return 0
    for b in api("/catalog/cover-requests")["books"]:
        rep = report(cur, books, b)
        print(b["title"], "→", rep["matched_by"], rep["outcome"], (rep.get("chosen") or {}).get("name", ""), flush=True)
        api("/catalog/covers", rep)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
