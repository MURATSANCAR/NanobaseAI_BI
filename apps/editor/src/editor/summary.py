"""Step 12: chapter and book summaries with book-director. Every summary
sentence is a SUMMARY claim with its own page quotes."""

from __future__ import annotations

import asyncio

from . import db, ledger, prompts, schemas
from .document import page_text_numbered
from .knowledge import DIRECTOR, _valid_pages, build_timeline, chapters
from .llm import Llm


def _save_sentences(generation_id: str, sentences: list[dict], *, subject: str, level: str,
                    call_id: int, extra: dict | None = None) -> int:
    n = 0
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)
        pages = _valid_pages(c, generation_id)
        for i, s in enumerate(sentences, start=1):
            evs = ledger.evidence_from_model(c, generation_id, idx, s["evidence"], valid_pages=pages)
            if ledger.save_claim(c, generation_id, kind="SUMMARY", subject=subject, claim=s["text"],
                                 evidence=evs, confidence=s["confidence"],
                                 created_by=f"summary:{level}", model_call_id=call_id,
                                 payload={"level": level, "order": i, **(extra or {})}):
                n += 1
    return n


async def chapter_summary(generation_id: str, ch: dict) -> dict:
    from .outputs import guard_legacy_producer
    guard_legacy_producer(generation_id)
    a, b = ch["page_from"], ch["page_to"]
    text = "\n".join(page_text_numbered(generation_id, p) for p in range(a, b + 1))
    evs = db.all_rows("SELECT page_from, page_to, modality, summary FROM event WHERE generation_id=%s"
                      " AND merged_into IS NULL AND page_from BETWEEN %s AND %s ORDER BY page_from",
                      generation_id, a, b)
    ref, body = prompts.render("chapter_summary", chapter_title=ch["title"], page_from=str(a),
                               page_to=str(b), pages_text=text, events="\n".join(
                                   f"- s{e['page_from']}-{e['page_to']} [{e['modality']}] {e['summary']}"
                                   for e in evs) or "-")
    out, call_id = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                                 prompt=ref, schema=schemas.SUMMARY,
                                                 pages=list(range(a, b + 1)), max_tokens=6000,
                                                 temperature=0.2, thinking=False)
    n = _save_sentences(generation_id, out["sentences"], subject=ch["title"], level="chapter",
                        call_id=call_id, extra={"pages": [a, b]})
    return {"chapter": ch["title"], "pages": [a, b], "sentences": n}


async def book_summary(generation_id: str) -> dict:
    from .outputs import guard_legacy_producer
    guard_legacy_producer(generation_id)
    chs = db.all_rows("SELECT subject, claim, source_pages FROM claim WHERE generation_id=%s AND"
                      " kind='SUMMARY' AND payload->>'level'='chapter' AND status NOT IN ('REJECTED','SUPERSEDED')"
                      " ORDER BY (payload->'pages'->>0)::int, (payload->>'order')::int", generation_id)
    q = {}
    for r in db.all_rows("SELECT c.id, e.page_no, e.quote FROM claim c JOIN claim_evidence ce ON"
                         " ce.claim_id=c.id JOIN evidence e ON e.id=ce.evidence_id WHERE"
                         " c.generation_id=%s AND c.kind='SUMMARY'", generation_id):
        q.setdefault(r["id"], []).append(f"s{r['page_no']}: “{r['quote']}”")
    chars = db.all_rows("SELECT canonical_name, aliases, description, identity_status FROM character"
                        " WHERE generation_id=%s ORDER BY first_page", generation_id)
    if not chs:
        return {"book_sentences": 0, "arcs": 0, "themes": 0, "skipped": "no chapter summaries"}
    ref, body = prompts.render(
        "book_summary",
        chapter_summaries="\n".join(f"[{r['subject']}] {r['claim']} (s{r['source_pages']})" for r in chs),
        characters="\n".join(f"- {c['canonical_name']} [{c['identity_status']}]: {c['description']}"
                             for c in chars) or "-",
        timeline="\n".join(f"{e['story_order']}. s{e['page_from']}: {e['summary']}"
                           for e in build_timeline(generation_id)) or "-")
    body += "\n\nKANIT ALINTILARI (bunlardan seç):\n" + "\n".join(x for v in q.values() for x in v)[:60000]
    out, call_id = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                                 prompt=ref, schema=schemas.BOOK_SUMMARY,
                                                 max_tokens=10000, temperature=0.2, thinking=True)
    n = _save_sentences(generation_id, out["summary"], subject="kitap", level="book", call_id=call_id)
    n_arc = _save_sentences(generation_id, [{"text": f"{a['character']}: {a['text']}",
                                              "evidence": a["evidence"], "confidence": a["confidence"]}
                                             for a in out["arcs"]],
                            subject="karakter yayı", level="arc", call_id=call_id)
    n_th = _save_sentences(generation_id, [{"text": f"{t['theme']}: {t['text']}",
                                             "evidence": t["evidence"], "confidence": t["confidence"]}
                                            for t in out["themes"]],
                           subject="tema", level="book_theme", call_id=call_id)
    return {"book_sentences": n, "arcs": n_arc, "themes": n_th}


async def all_summaries(generation_id: str) -> dict:
    chs = chapters(generation_id)
    res = await asyncio.gather(*(chapter_summary(generation_id, c) for c in chs))
    book = await book_summary(generation_id)
    return {"chapters": res, "book": book}
