"""The editor review queue, as one implementation for both the CLI and the card service.

An analysis stops and asks instead of guessing: an actor the text does not name uniquely,
a drawing that contradicts the sentence, a page the extractor reads as non-story. Until
someone decides, the generation cannot be accepted (`foundation.readiness`:
`OPEN_EDITOR_REVIEW` can never be waived).

A decision is not a status flip. `correct` is written to `editor_correction`, which
`ledger.corrections_for_book` carries into every later reading of the same book, so the
same question is not asked twice.

The queue is served per BOOK, not per generation: a reviewer opens a book, and the newest
generation is the one they are shown (the same generation a reader is served). Page images
and figure crops come from the files the analysis already produced, so a reviewer can see
what the disagreement is about — a TEXT_VISUAL contradiction cannot be judged from text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import db, jobs

DECISIONS = {"approve": ("APPROVED", "EDITOR_APPROVED", "EDITOR_DISMISSED"),
             "reject": ("REJECTED", "EDITOR_REJECTED", "EDITOR_DISMISSED"),
             "correct": ("CORRECTED", "EDITOR_CORRECTED", "EDITOR_CONFIRMED")}


def _newest_generation(book_id: str) -> dict:
    row = db.one("SELECT g.id::text AS id, g.code_version, bv.id::text AS book_version_id, b.title"
                 " FROM generation g JOIN book_version bv ON bv.id=g.book_version_id"
                 " JOIN book b ON b.id=bv.book_id WHERE b.id=%s"
                 " ORDER BY g.created_at DESC, g.id DESC LIMIT 1", book_id)
    if row is None:
        raise KeyError(f"book {book_id} has no generation")
    return row


def queue(book_id: str, status: str = "OPEN", limit: int = 200) -> dict:
    """Open review items of the book's newest generation, worst priority first."""
    gen = _newest_generation(book_id)
    items = jobs.list_review_queue(gen["id"], status, limit)
    counts = db.all_rows("SELECT status, count(*) AS n FROM review_item WHERE generation_id=%s"
                         " GROUP BY status", gen["id"])
    # `reason` carries the human sentence; its prefix is the machine's question type and is
    # what a bulk decision selects on ("Sayfa türü incelemesi: s47; ..."). The page in some
    # prefixes ("TEXT_VISUAL aday çelişki (s[23])") is dropped, or every page would be its
    # own kind and the thirteen-questions-one-judgement case would never group.
    for it in items:
        it["id"] = str(it["id"])
        it["kind"] = str(it["reason"]).split(":")[0].split(" (")[0].strip()
    return {"book_id": book_id, "title": gen["title"], "generation_id": gen["id"],
            "code_version": gen["code_version"], "items": items,
            "counts": {r["status"]: r["n"] for r in counts},
            "open": sum(r["n"] for r in counts if r["status"] == "OPEN")}


def decide(item_id: str, decision: str, editor: str, data: dict | None = None) -> dict:
    """One decision. `correct` needs the correction itself; it is kept for later readings."""
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision}")
    if not (editor or "").strip():
        raise ValueError("the deciding editor must be named")
    status, claim_status, contradiction_status = DECISIONS[decision]
    with db.tx() as c:
        it = c.execute("SELECT r.*, bv.book_id FROM review_item r JOIN generation g ON g.id=r.generation_id"
                       " JOIN book_version bv ON bv.id=g.book_version_id WHERE r.id=%s", (item_id,)).fetchone()
        if it is None:
            raise KeyError(f"review item {item_id} not found")
        if it["status"] != "OPEN":
            raise ValueError(f"already decided: {it['status']}")
        if decision == "correct" and not data:
            raise ValueError("a correction is required for 'correct'")
        c.execute("UPDATE review_item SET status=%s, decided_by=%s, decision=%s, decided_at=now() WHERE id=%s",
                  (status, editor, db.J(data or {}), item_id))
        if it["claim_id"]:
            c.execute("UPDATE claim SET status=%s WHERE id=%s", (claim_status, it["claim_id"]))
        if it["contradiction_id"]:
            c.execute("UPDATE contradiction SET status=%s WHERE id=%s", (contradiction_status, it["contradiction_id"]))
        if decision == "correct":
            cl = c.execute("SELECT kind, subject, claim FROM claim WHERE id=%s", (it["claim_id"],)).fetchone() \
                if it["claim_id"] else None
            c.execute("INSERT INTO editor_correction(book_id, review_item_id, target_kind, target_key,"
                      " correction, editor) VALUES (%s,%s,%s,%s,%s,%s)",
                      (it["book_id"], item_id, data.get("target_kind") or (cl or {}).get("kind", "CLAIM"),
                       data.get("target_key") or (cl or {}).get("subject") or (cl or {}).get("claim", "")[:200],
                       db.J(data), editor))
    return {"item": item_id, "status": status, "decided_by": editor}


def decide_many(book_id: str, item_ids: list[str], decision: str, editor: str,
                data: dict | None = None) -> dict:
    """The same decision for several items — thirteen 'is this page part of the story?'
    questions are one judgement, not thirteen. Every item is still decided on its own row
    with its own reason, so nothing is closed in bulk without a trace; an item that cannot
    be decided (already closed, not this book's) is reported, not silently skipped."""
    # A bad decision or a nameless caller is one error about the request, not N errors
    # about the items: it is refused before anything is written.
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision}")
    if not (editor or "").strip():
        raise ValueError("the deciding editor must be named")
    if decision == "correct" and not data:
        raise ValueError("a correction is required for 'correct'")
    gen = _newest_generation(book_id)
    mine = {str(r["id"]) for r in db.all_rows(
        "SELECT id FROM review_item WHERE generation_id=%s AND status='OPEN'", gen["id"])}
    done, failed = [], []
    for item_id in item_ids:
        if item_id not in mine:
            failed.append({"item": item_id, "error": "not an open item of this book"})
            continue
        try:
            done.append(decide(item_id, decision, editor, data))
        except Exception as e:  # noqa: BLE001 — one bad item must not undo the others
            failed.append({"item": item_id, "error": str(e)})
    return {"book_id": book_id, "generation_id": gen["id"], "decided": len(done),
            "failed": failed, "items": done}


# Where a re-cut crop goes when the storage is mounted read-only. The card service reads
# the analysis's files; it does not write into them, so a crop it has to produce itself is
# scratch, not a record — the gallery under `storage` stays the analysis's own.
SCRATCH = Path("/tmp/editor-review-crops")


def _rendered_page(gen: dict, page_no: int) -> Path:
    from .document import render_page
    row = db.one("SELECT render_path FROM page WHERE book_version_id=%s AND page_no=%s",
                 gen["book_version_id"], page_no)
    if row is None:
        raise KeyError(f"page {page_no} not found")
    existing = Path(row["render_path"]) if row["render_path"] else None
    if existing and existing.exists():
        return existing
    try:
        return Path(render_page(gen["book_version_id"], page_no)["path"])
    except OSError as e:      # read-only storage and the render was never made
        raise KeyError(f"page {page_no} has no render: {e}") from None


def page_image(book_id: str, page_no: int) -> Path:
    """The page as the analysis saw it."""
    return _rendered_page(_newest_generation(book_id), page_no)


def figure_image(book_id: str, region_id: str) -> Path:
    """One figure, cut out of its page render. The crop is a cache: the analysis writes it
    into the book's gallery, and it is re-cut here when that generation's gallery has been
    pruned away (see `gallery.py`) — into scratch, so a read-only storage mount still works."""
    from .vision import _crop
    gen = _newest_generation(book_id)
    row = db.one("SELECT page_no, bbox FROM visual_region WHERE id=%s AND generation_id=%s",
                 region_id, gen["id"])
    if row is None or not row["bbox"]:
        raise KeyError(f"figure {region_id} not found")
    page = _rendered_page(gen, row["page_no"])
    kept = page.parent / "gallery" / gen["id"] / f"fig-{region_id}.png"
    if kept.exists():
        return kept
    out = SCRATCH / gen["id"] / f"fig-{region_id}.png"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    return _crop(str(page), row["bbox"], out)


def page_context(book_id: str, page_no: int) -> dict[str, Any]:
    """What the analysis read on a page: its text and the figures it found there. This is
    the evidence a reviewer judges a page-role or text/visual question against."""
    gen = _newest_generation(book_id)
    texts = db.all_rows("SELECT source, text FROM page_text WHERE generation_id=%s AND page_no=%s"
                        " ORDER BY source", gen["id"], page_no)
    regions = db.all_rows("SELECT id::text AS id, label, kind, bbox, description FROM visual_region"
                          " WHERE generation_id=%s AND page_no=%s ORDER BY kind, label",
                          gen["id"], page_no)
    return {"book_id": book_id, "generation_id": gen["id"], "page_no": page_no,
            "texts": texts, "regions": regions}
