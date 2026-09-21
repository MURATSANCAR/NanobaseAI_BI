"""Catalog: book cards, covers and search across books.

A card is built when an analysis is sealed, only from the ledger: claims the
Critic verified (or an editor approved), confirmed characters, key events by
narrative role, bibliographic metadata whose quote was found verbatim on a
front-matter page. Recommendations are therefore answers with page citations,
not the agent's opinion of a book."""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from pathlib import Path

import pymupdf
from qdrant_client import models

from . import db, ledger, prompts, schemas
from .config import settings
from .document import page_text_numbered
from .knowledge import DIRECTOR, _valid_pages
from .llm import Llm
from .retrieval import DIM, NS, qdrant, rerank_evidence

CATALOG = "editor_catalog_v1"
OK = ("VERIFIED", "EDITOR_APPROVED", "EDITOR_CORRECTED")
QUERY_INSTRUCTION = ("Given a reader's request for a book, retrieve the themes, summaries and "
                     "events of books that match the request")
ROLE_TR = {"SETUP": "giriş", "INCITING": "tetikleyici olay", "TURNING_POINT": "dönüm noktası",
           "CLIMAX": "doruk", "RESOLUTION": "çözüm"}
COVER_EXT = {".png", ".jpg", ".jpeg", ".webp"}


# ------------------------------------------------------------- metadata
async def extract_metadata(generation_id: str) -> dict:
    """Bibliographic fields from the front matter, each kept only if its quote is
    found verbatim on the page (a METADATA claim with evidence)."""
    have = db.all_rows("SELECT subject, claim, source_pages, id FROM claim WHERE generation_id=%s AND"
                       " kind='METADATA' AND status = ANY(%s)", generation_id, list(OK))
    if have:
        return _metadata_dict(have)
    sealed = db.one("SELECT sealed_at FROM generation WHERE id=%s", generation_id)
    if sealed is None or sealed["sealed_at"] is not None:
        # The regression suite caught this: building a card once wrote METADATA claims into
        # an already sealed generation. A sealed generation is read-only; its card simply
        # has no bibliographic block until the book is analysed again.
        return {}
    pages = [r["page_no"] for r in db.all_rows(
        "SELECT page_no FROM page_role WHERE generation_id=%s AND role='FRONT_MATTER' ORDER BY 1",
        generation_id)]
    if not pages:
        return {}
    ref, body = prompts.render("book_metadata", pages_text="\n".join(
        page_text_numbered(generation_id, p) for p in pages))
    out, call_id = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                                 prompt=ref, schema=schemas.BOOK_METADATA, pages=pages,
                                                 max_tokens=3000, temperature=0.0, thinking=False)
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)
        valid = _valid_pages(c, generation_id)
        for f in out["fields"]:
            if not f["value"].strip():
                continue
            evs = [e for e in ledger.evidence_from_model(
                c, generation_id, idx, [{"page": f["page"], "paragraph": next((s["idx"] for s in idx.matching_spans(f["page"], f["quote"])), 0), "quote": f["quote"]}],
                valid_pages=valid) if e[1]]
            if evs:     # verbatim on the page, or it does not exist
                ledger.save_claim(c, generation_id, kind="METADATA", subject=f["field"],
                                  claim=f["value"].strip(), evidence=evs, confidence=0.95,
                                  created_by="catalog:metadata", model_call_id=call_id,
                                  status="VERIFIED")
    return _metadata_dict(db.all_rows(
        "SELECT subject, claim, source_pages, id FROM claim WHERE generation_id=%s AND kind='METADATA'"
        " AND status = ANY(%s)", generation_id, list(OK)))


def _metadata_dict(rows: list[dict]) -> dict:
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r["subject"], []).append(
            {"value": r["claim"], "pages": r["source_pages"], "claim_id": str(r["id"])})
    return out


def _ages(meta: dict) -> tuple[int | None, int | None]:
    nums = [int(n) for a in meta.get("AGE_RANGE", []) for n in re.findall(r"\d{1,2}", a["value"])]
    return (min(nums), max(nums)) if nums else (None, None)


# ---------------------------------------------------------------- covers
def _book_dir(book_version_id: str) -> Path:
    bv = db.one("SELECT file_path FROM book_version WHERE id=%s", book_version_id)
    return Path(bv["file_path"]).parent


def current_cover(book_id: str) -> dict | None:
    return db.one("SELECT id, source, file_path, page_no, width_px, height_px FROM book_cover WHERE"
                  " book_id=%s AND is_current", book_id)


def _store_cover(book_id: str, source: str, path: Path, page_no: int | None, added_by: str) -> dict:
    pm = pymupdf.Pixmap(str(path))
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    with db.tx() as c:
        c.execute("UPDATE book_cover SET is_current=false WHERE book_id=%s AND is_current", (book_id,))
        row = c.execute(
            "INSERT INTO book_cover(book_id, source, file_path, page_no, sha256, width_px, height_px,"
            " added_by) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (book_id, source, str(path), page_no, sha, pm.width, pm.height, added_by)).fetchone()
    return {"cover_id": str(row["id"]), "source": source, "file_path": str(path)}


def set_uploaded_cover(book_id: str, file_name: str, added_by: str) -> dict:
    """An uploaded cover (from storage/covers-inbox) replaces whatever is current."""
    src = (settings().storage / "covers-inbox" / Path(file_name).name).resolve()
    if src.parent != (settings().storage / "covers-inbox").resolve() or not src.is_file() \
            or src.suffix.lower() not in COVER_EXT:
        raise FileNotFoundError(f"{file_name}: covers-inbox içinde bir görsel değil")
    bv = db.one("SELECT id FROM book_version WHERE book_id=%s ORDER BY created_at DESC LIMIT 1", book_id)
    if bv is None:
        raise KeyError(f"book {book_id} not found")
    dest = _book_dir(str(bv["id"])) / f"cover-{hashlib.sha256(src.read_bytes()).hexdigest()[:12]}{src.suffix.lower()}"
    shutil.copyfile(src, dest)
    return _store_cover(book_id, "UPLOADED", dest, None, added_by)


PRIORITY = {"UPLOADED": 4, "CRM": 3, "WEB": 2, "PDF_PAGE": 1}


def cover_requests() -> list[dict]:
    """Books whose current cover is not an editor upload: the CRM connector looks these up
    (again on every run, so a newer CRM image replaces an older one)."""
    rows = db.all_rows(
        "SELECT c.book_id, c.title, c.metadata, cv.source, cv.source_date FROM book_card c LEFT JOIN"
        " book_cover cv ON cv.book_id=c.book_id AND cv.is_current WHERE c.is_current AND"
        " coalesce(cv.source,'PDF_PAGE') <> 'UPLOADED'")
    return [{"book_id": str(r["book_id"]), "title": r["title"],
             "isbns": [x["value"] for x in (r["metadata"] or {}).get("ISBN", [])],
             "current_source": r["source"], "current_date": str(r["source_date"]) if r["source_date"] else None}
            for r in rows]


def store_lookup(rep: dict, source: str, data: bytes | None = None) -> dict:
    """Result of one cover lookup (CRM connector or publisher web site). A fetched image
    becomes the book's cover when its source outranks the current one (UPLOADED > CRM >
    WEB > PDF_PAGE), or has the same rank and is a different, newer image."""
    import base64
    from datetime import datetime
    book_id = rep["book_id"]
    outcome, stored = rep["outcome"], None
    if outcome == "STORED":
        data = data if data is not None else base64.b64decode(rep["image_b64"])
        chosen = rep["chosen"]
        cur = db.one("SELECT source, source_date, sha256 FROM book_cover WHERE book_id=%s AND is_current",
                     book_id)
        sha = hashlib.sha256(data).hexdigest()
        when = datetime.fromisoformat(chosen["date"])
        rank, cur_rank = PRIORITY[source], PRIORITY[(cur or {}).get("source") or "PDF_PAGE"] if cur else 0
        newer = not cur or not cur["source_date"] or \
            when.replace(tzinfo=None) > cur["source_date"].replace(tzinfo=None)
        if cur and cur_rank > rank:
            outcome = "KEPT_" + cur["source"]
        elif cur and cur_rank == rank and (cur["sha256"] == sha or not newer):
            outcome = "KEPT_CURRENT"
        else:
            bv = db.one("SELECT id FROM book_version WHERE book_id=%s ORDER BY created_at DESC LIMIT 1", book_id)
            ext = Path(rep.get("file_name") or "cover.jpg").suffix.lower()
            ext = ext if ext in COVER_EXT else ".jpg"
            dest = _book_dir(str(bv["id"])) / f"cover-{source.lower()}-{sha[:12]}{ext}"
            dest.write_bytes(data)
            stored = _store_cover(book_id, source, dest, None, f"{source.lower()}-sync")
            db.one("UPDATE book_cover SET source_date=%s, source_ref=%s WHERE id=%s RETURNING id", when,
                   db.J({"crm_book_id": rep.get("crm_book_id"), "matched_by": rep.get("matched_by"),
                         "kind": chosen["kind"], "path": chosen["path"], "name": chosen.get("name")}),
                   stored["cover_id"])
    db.one("INSERT INTO cover_lookup(book_id, source, matched_by, crm_book_id, crm_title, candidates, chosen,"
           " outcome, detail) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id", book_id, source,
           rep.get("matched_by"), rep.get("crm_book_id"), rep.get("crm_title"),
           db.J(rep.get("candidates") or []), db.J(rep["chosen"]) if rep.get("chosen") else None,
           outcome, rep.get("detail"))
    return {"book_id": book_id, "source": source, "outcome": outcome, "cover": stored}


def store_crm_lookup(rep: dict) -> dict:
    return store_lookup(rep, "CRM")


def ensure_cover(book_id: str, generation_id: str) -> dict | None:
    """Until a cover is uploaded: the most illustrated front-matter page of the PDF
    (else the most illustrated page of the book) stands in, marked PDF_PAGE."""
    cur = current_cover(book_id)
    if cur:
        return cur
    pick = db.one(
        "SELECT p.page_no, p.render_path FROM page p JOIN generation g ON g.book_version_id="
        "p.book_version_id LEFT JOIN page_role r ON r.generation_id=g.id AND r.page_no=p.page_no"
        " WHERE g.id=%s AND coalesce(p.nontext_ink,0) >= %s ORDER BY (r.role='FRONT_MATTER') DESC"
        " NULLS LAST, p.nontext_ink DESC LIMIT 1", generation_id, settings().min_illustration_ink)
    if pick is None:
        return None
    _store_cover(book_id, "PDF_PAGE", Path(pick["render_path"]), pick["page_no"], "catalog")
    return current_cover(book_id)


# ------------------------------------------------------------------ card
def _claims(generation_id: str, where: str, *args) -> list[dict]:
    return db.all_rows("SELECT id, subject, claim, source_pages, payload FROM claim WHERE generation_id"
                       f"=%s AND status = ANY(%s) AND {where}", generation_id, list(OK), *args)


async def build_card(generation_id: str) -> dict:
    gen = db.one("SELECT g.id, g.sealed_at, g.book_version_id, bv.book_id, b.title FROM generation g"
                 " JOIN book_version bv ON bv.id=g.book_version_id JOIN book b ON b.id=bv.book_id"
                 " WHERE g.id=%s", generation_id)
    if gen is None or gen["sealed_at"] is None:
        raise ValueError("kart yalnız tamamlanmış (mühürlü) nesilden kurulur")
    meta = await extract_metadata(generation_id)
    title = (meta.get("TITLE") or [{"value": gen["title"]}])[0]["value"]
    age_min, age_max = _ages(meta)
    summary = [{"text": r["claim"], "pages": r["source_pages"], "claim_id": str(r["id"])}
               for r in sorted(_claims(generation_id, "kind='SUMMARY' AND payload->>'level'='book'"),
                               key=lambda r: int(r["payload"].get("order", 0)))]
    themes = [{"theme": r["subject"], "text": r["claim"], "pages": r["source_pages"], "claim_id": str(r["id"])}
              for r in _claims(generation_id, "kind='THEME' AND payload->>'level'='book'")]
    chars = db.all_rows("SELECT canonical_name AS name, aliases, description FROM character WHERE"
                        " generation_id=%s AND identity_status='CONFIRMED' ORDER BY first_page", generation_id)
    events = [{"role": r["narrative_role"], "text": r["summary"], "pages": [r["page_from"]],
               "claim_id": str(r["claim_id"])}
              for r in db.all_rows(
                  "SELECT e.narrative_role, e.summary, e.page_from, e.claim_id FROM event e JOIN claim c"
                  " ON c.id=e.claim_id WHERE e.generation_id=%s AND e.merged_into IS NULL AND"
                  " e.narrative_role IS NOT NULL AND e.narrative_role<>'ORDINARY' AND c.status = ANY(%s)"
                  " ORDER BY e.story_order", generation_id, list(OK))]
    names = lambda k: ", ".join(x["value"] for x in meta.get(k, []))  # noqa: E731
    card_text = "\n".join(x for x in [
        f"Kitap: {title}", f"Yazar: {names('AUTHOR')}" if meta.get("AUTHOR") else "",
        f"Yaş: {names('AGE_RANGE')}" if meta.get("AGE_RANGE") else "",
        f"Tür: {names('GENRE')}" if meta.get("GENRE") else "",
        "Özet: " + " ".join(s["text"] for s in summary),
        "Temalar: " + "; ".join(f"{t['theme']}: {t['text']}" for t in themes),
        "Karakterler: " + "; ".join(f"{c['name']}: {c['description']}" for c in chars),
        "Kilit olaylar: " + "; ".join(e["text"] for e in events)] if x)
    with db.tx() as c:
        c.execute("UPDATE book_card SET is_current=false WHERE book_id=%s AND is_current", (gen["book_id"],))
        card = c.execute(
            "INSERT INTO book_card(book_id, book_version_id, generation_id, title, metadata, age_min,"
            " age_max, summary, themes, characters, key_events, card_text) VALUES"
            " (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (gen["book_id"], gen["book_version_id"], generation_id, title, db.J(meta), age_min, age_max,
             db.J(summary), db.J(themes), db.J(chars), db.J(events), card_text)).fetchone()
    cover = ensure_cover(str(gen["book_id"]), generation_id)
    try:                                   # publisher web site, by ISBN; never blocks the card
        from . import web_cover
        web = await web_cover.sync_book(str(gen["book_id"]))
        cover = current_cover(str(gen["book_id"])) or cover
    except Exception as e:  # noqa: BLE001
        web = {"outcome": "ERROR", "detail": str(e)[:300]}
    n = await _index(str(gen["book_id"]), str(card["id"]), title, summary, themes, events, card_text)
    return {"card_id": str(card["id"]), "book_id": str(gen["book_id"]), "title": title,
            "metadata_fields": sorted(meta), "summary": len(summary), "themes": len(themes),
            "characters": len(chars), "key_events": len(events), "indexed_facets": n,
            "cover": (cover or {}).get("source"), "web_cover": web.get("outcome")}


async def _index(book_id: str, card_id: str, title: str, summary, themes, events, card_text) -> int:
    q = qdrant()
    if not await q.collection_exists(CATALOG):
        await q.create_collection(CATALOG, vectors_config=models.VectorParams(
            size=DIM, distance=models.Distance.COSINE))
        await q.create_payload_index(CATALOG, "book_id", models.PayloadSchemaType.KEYWORD)
    facets = [{"facet": "card", "text": card_text[:6000], "pages": []}]
    facets += [{"facet": "summary", "text": s["text"], "pages": s["pages"]} for s in summary]
    facets += [{"facet": "theme", "text": f"{t['theme']}: {t['text']}", "pages": t["pages"]} for t in themes]
    facets += [{"facet": "event", "text": e["text"], "pages": e["pages"], "role": e["role"]} for e in events]
    vecs = await Llm(None).embed([f["text"] for f in facets])
    await q.delete(CATALOG, points_selector=models.FilterSelector(filter=models.Filter(must=[
        models.FieldCondition(key="book_id", match=models.MatchValue(value=book_id))])))
    await q.upsert(CATALOG, points=[models.PointStruct(
        id=str(uuid.uuid5(NS, f"catalog:{card_id}:{i}")), vector=v,
        payload={**f, "book_id": book_id, "card_id": card_id, "title": title})
        for i, (f, v) in enumerate(zip(facets, vecs))])
    return len(facets)


# ---------------------------------------------------------------- search
def get_book_card(book_id: str) -> dict | None:
    card = db.one("SELECT id AS card_id, book_id, generation_id, title, metadata, age_min, age_max,"
                  " summary, themes, characters, key_events, created_at FROM book_card WHERE book_id=%s"
                  " AND is_current", book_id)
    if card:
        card["cover"] = _cover_ref(book_id)
    return card


SOURCE_TR = {"UPLOADED": "editörün yüklediği kapak", "CRM": "CRM'deki kapak",
             "WEB": "yayıncının sitesindeki kapak", "PDF_PAGE": "kitabın içinden (kapak bulunamadı)"}
OUTCOME_TR = {"STORED": "alındı", "NO_MATCH": "kitap eşleşmedi", "NO_IMAGE": "görsel yok",
              "FETCH_FAILED": "eşleşti, dosya okunamadı", "AMBIGUOUS": "birden çok kayıt eşleşti",
              "KEPT_CURRENT": "eldeki kapak güncel", "KEPT_UPLOADED": "editörün kapağı korundu",
              "KEPT_CRM": "CRM kapağı korundu", "KEPT_WEB": "site kapağı korundu"}


def _cover_ref(book_id: str) -> dict | None:
    """The cover the screens show, where it came from, and what each source answered the
    last time it was asked (so the UI can say WHY this is the cover)."""
    cov = current_cover(book_id)
    if cov is None:
        return None
    looks = db.all_rows("SELECT DISTINCT ON (source) source, outcome, matched_by, detail, created_at FROM"
                        " cover_lookup WHERE book_id=%s ORDER BY source, created_at DESC", book_id)
    return {"url": f"/covers/{book_id}", "source": cov["source"], "source_label": SOURCE_TR[cov["source"]],
            "page_no": cov["page_no"],
            "lookups": [{"source": l["source"], "outcome": l["outcome"],
                         "outcome_label": OUTCOME_TR.get(l["outcome"], l["outcome"]),
                         "matched_by": l["matched_by"], "detail": l["detail"],
                         "at": str(l["created_at"])} for l in looks]}


async def search_books(query: str, k: int = 5, age: int | None = None) -> list[dict]:
    """Books whose verified themes, summary or key events match the request. Every
    reason returned carries its page citations."""
    q = qdrant()
    if not await q.collection_exists(CATALOG):
        return []
    vec = (await Llm(None).embed([query], instruction=QUERY_INSTRUCTION))[0]
    hits = (await q.query_points(CATALOG, query=vec, limit=120, with_payload=True)).points
    by_book: dict[str, list] = {}
    for h in hits:
        by_book.setdefault(h.payload["book_id"], []).append(h)
    cards = {str(r["book_id"]): r for r in db.all_rows(
        "SELECT book_id, title, metadata, age_min, age_max, card_text FROM book_card WHERE is_current"
        " AND book_id = ANY(%s::uuid[])", list(by_book))}
    books = [b for b in by_book if b in cards and (
        age is None or cards[b]["age_min"] is None or cards[b]["age_min"] <= age <= (cards[b]["age_max"] or 99))]
    if not books:
        return []
    ranked = await rerank_evidence(query, [cards[b]["card_text"][:6000] for b in books])
    out = []
    for r in ranked[:k]:
        b = books[r["index"]]
        card, meta = cards[b], cards[b]["metadata"]
        why = [{"facet": h.payload["facet"], "text": h.payload["text"], "pages": h.payload["pages"],
                "score": round(h.score, 3)}
               for h in sorted(by_book[b], key=lambda h: -h.score) if h.payload["facet"] != "card"][:4]
        out.append({"book_id": b, "title": card["title"], "match_score": round(r["score"], 4),
                    "authors": [x["value"] for x in meta.get("AUTHOR", [])],
                    "age_range": [x["value"] for x in meta.get("AGE_RANGE", [])],
                    "genre": [x["value"] for x in meta.get("GENRE", [])],
                    "cover": _cover_ref(b), "why": why})
    return out


async def rebuild_all() -> list[dict]:
    """Card for every book from its latest sealed generation (same function the
    workflow runs at the end of an analysis)."""
    gens = db.all_rows("SELECT DISTINCT ON (bv.book_id) g.id FROM generation g JOIN book_version bv ON"
                       " bv.id=g.book_version_id WHERE g.sealed_at IS NOT NULL ORDER BY bv.book_id,"
                       " g.created_at DESC")
    return [await build_card(str(g["id"])) for g in gens]
