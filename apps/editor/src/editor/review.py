"""The editor review queue, as one implementation for both the CLI and the card service.

An analysis stops and asks instead of guessing: an actor the text does not name uniquely,
a drawing that contradicts the sentence, a page the extractor reads as non-story. Until
someone decides, the generation cannot be accepted (`foundation.readiness`:
`OPEN_EDITOR_REVIEW` can never be waived).

A decision is not a status flip: each button does what it says to the reading (see
`choose`). A correction is written to `editor_correction`, which `ledger.corrections_for_book`
carries into every later reading of the same book, so the same question is not asked twice.

The queue is served per BOOK, not per generation: a reviewer opens a book, and the newest
generation is the one they are shown (the same generation a reader is served). Page images
and figure crops come from the files the analysis already produced, so a reviewer can see
what the disagreement is about — a TEXT_VISUAL contradiction cannot be judged from text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import db

def _newest_generation(book_id: str) -> dict:
    row = db.one("SELECT g.id::text AS id, g.code_version, bv.id::text AS book_version_id, b.title"
                 " FROM generation g JOIN book_version bv ON bv.id=g.book_version_id"
                 " JOIN book b ON b.id=bv.book_id WHERE b.id=%s"
                 " ORDER BY g.created_at DESC, g.id DESC LIMIT 1", book_id)
    if row is None:
        raise KeyError("Bu kitabın okuması yok.")
    return row


# ----------------------------------------------------------------- what the editor sees
# The analysis writes its questions for itself: «Olay kipi çözülemedi: çıkarım PLAN, kontrol
# MEMORY … hakem REALIZED (0.90)», «Critic: düşük güven 0.21 — Kanıt 'gazing outward'…». None
# of that reaches the screen. An editor is shown, for every item: one question in plain
# Turkish, the finding it is about, the book's own sentence it rests on, the page as a
# picture, and buttons that say what they will do. The machine note stays in the database.
#
# A picture's English description (the vision model writes in English) is never quoted: a
# finding that rests on a drawing is shown with the drawing. A finding whose own wording is
# English is replaced by a Turkish sentence that points at the picture.

CLAIM_KIND = {"EVENT": "Olay", "EMOTION": "Duygu", "VISUAL_SCENE": "Sahne", "THEME": "Tema",
              "CHARACTER_IDENTITY": "Karakter", "SUMMARY": "Özet", "VISUAL_CONTINUITY": "Çizim",
              "TEXT_VISUAL_MISMATCH": "Metin ve çizim"}
MODALITY = {"REALIZED": "gerçekten yaşanan bir olay", "MEMORY": "geçmişte yaşanmış bir anı",
            "PLAN": "henüz yaşanmamış bir plan", "IMAGINATION": "bir hayal", "DREAM": "bir rüya",
            "JOKE": "bir şaka"}
GROUP = {  # type -> (title shown over the group, whether one answer may close the whole group)
    "page": ("Hikâye dışı görünen sayfalar", True),
    "conflict_text_visual": ("Metin ile çizim uyuşuyor mu?", True),
    "conflict_continuity": ("Çizimler kendi arasında tutarlı mı?", True),
    "conflict_identity": ("Çizimdeki karakter doğru tanınmış mı?", True),
    "modality": ("Olay gerçekten yaşanıyor mu?", False),
    "actor": ("Olaydaki kişiler", False),
    "identity": ("Karakterin kimliği", False),
    "fact": ("Tespitler kitaba uyuyor mu?", True),
    "proofing": ("Son okuma bulguları", False),
}
ORDER = list(GROUP)

_EN = re.compile(r"\b(the|of|and|with|is|are|was|his|her|inferred|looks?|looking|holding|gazing|"
                 r"window|mother|father|woman|man|girl|boy|child|standing|sitting|appears?)\b", re.I)


_FIGURE_LABEL = re.compile(r"\bF\d+:\s*")   # the continuity check's own figure numbering


def _turkish(text: str | None) -> str | None:
    """The text as it is — minus the analysis's figure numbering («F2: sayfa 105'de…») — or
    None when it is (partly) English and must not be shown."""
    text = _FIGURE_LABEL.sub("", (text or "")).strip()
    return None if not text or _EN.search(text) else text


def _names(fragment: str) -> list[str]:
    """«Ayfersu (yok 0.99), Süheyla (0.97)» -> ['Ayfersu', 'Süheyla'] — the format
    knowledge.event_actors writes; only the names are kept, never the numbers."""
    return [n.strip() for n in re.findall(r"([^,()]+?)\s*\((?:yok\s*)?[\d.]+\)", fragment) if n.strip()]


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " ve " + names[-1]


def _type(it: dict) -> str:
    if it["proof_run_id"]:
        return "proofing"
    if it["page_role_page_no"] is not None:
        return "page"
    if it["contradiction_id"]:
        k = (it["contradiction_kind"] or "").upper()
        return {"TEXT_VISUAL": "conflict_text_visual", "CONTINUITY": "conflict_continuity",
                "IDENTITY": "conflict_identity"}.get(k, "conflict_text_visual")
    reason = it["reason"] or ""
    if reason.startswith("Kim yaptı"):
        return "actor"
    if reason.startswith("Olay kipi"):
        return "modality"
    if reason.startswith("Karakter kimliği"):
        return "identity"
    return "fact"


def _actor_question(reason: str) -> dict | None:
    """Kim yaptı: which names the two readings dispute, and in which direction."""
    absent = re.search(r"olayda görmüyor:\s*(.+?)(?:;|$)", reason)
    doer = re.search(r"eylemi yapan(?: diyor)?:\s*(.+?)(?:;|$)", reason)
    if absent and _names(absent.group(1)):
        return {"direction": "absent", "names": _names(absent.group(1))}
    if doer and _names(doer.group(1)):
        return {"direction": "doer", "names": _names(doer.group(1))}
    return None


def _view(it: dict, quote: dict | None, figures: list[str]) -> dict:
    """Everything the screen shows for one item, in Turkish, and nothing else."""
    typ = _type(it)
    kind = CLAIM_KIND.get(it["claim_kind"] or "", "Tespit")
    finding = _turkish(it["claim"])
    pages = sorted({*(it["source_pages"] or []), *(it["pages"] or [])}
                   | ({it["page_role_page_no"]} if it["page_role_page_no"] is not None else set()))
    v: dict[str, Any] = {"id": str(it["id"]), "type": typ, "priority": it["priority"],
                         "pages": pages, "subject": kind, "quote": quote, "figures": figures,
                         "statement": finding, "actions": [], "link": None}
    fix = {"key": "fix", "label": "Düzelt", "tone": "ghost"}
    if typ == "page":
        p = it["page_role_page_no"]
        v.update(subject="Sayfa", statement=f"{p}. sayfa hikâyenin dışında görünüyor "
                 "(künye, içindekiler, tanıtım ya da boş sayfa olabilir).",
                 question=f"{p}. sayfa hikâyenin dışında mı?",
                 actions=[{"key": "yes", "label": "Evet, hikâye dışı", "tone": "primary"},
                          {"key": "no", "label": "Hayır, hikâyenin parçası", "tone": "ghost"}])
    elif typ.startswith("conflict"):
        v.update(subject={"conflict_text_visual": "Metin ve çizim", "conflict_continuity": "Çizim",
                          "conflict_identity": "Karakter"}[typ],
                 statement=_turkish(it["description"]) or "Bu sayfadaki çizim metinle uyuşmuyor olabilir.",
                 question={"conflict_text_visual": "Metinde anlatılanla çizim çelişiyor mu?",
                           "conflict_continuity": "Bu çizim önceki sayfalardakiyle çelişiyor mu?",
                           "conflict_identity": "Çizimdeki karakter yanlış mı tanınmış?"}[typ],
                 actions=[{"key": "yes", "label": "Evet, çelişiyor", "tone": "primary"},
                          {"key": "no", "label": "Hayır, sorun yok", "tone": "ghost"}, fix])
    elif typ == "actor":
        q = _actor_question(it["reason"] or "")
        if q and q["direction"] == "absent":
            who = _and(q["names"])
            v.update(question=f"{who} bu olayda yer alıyor mu?",
                     actions=[{"key": "yes", "label": f"Evet, {who} bu olayda", "tone": "primary"},
                              {"key": "no", "label": "Hayır, yer almıyor", "tone": "ghost"}])
        elif q:
            who = _and(q["names"])
            v.update(question=f"Bu olayı {who} mı yapıyor?",
                     actions=[{"key": "yes", "label": f"Evet, {who} yapıyor", "tone": "primary"},
                              {"key": "no", "label": "Hayır", "tone": "ghost"}])
        else:
            v.update(question="Bu olaydaki kişiler doğru mu?",
                     actions=[{"key": "yes", "label": "Doğru", "tone": "primary"}, fix])
    elif typ == "modality":
        what = MODALITY.get((it["payload"] or {}).get("modality") or "REALIZED", MODALITY["REALIZED"])
        v.update(question=f"Bu, kitapta {what} mı?",
                 actions=[{"key": "yes", "label": "Evet", "tone": "primary"},
                          {"key": "no", "label": "Hayır", "tone": "ghost"}, fix])
    elif typ == "identity":
        v.update(question="Bu kimlik doğru mu?",
                 actions=[{"key": "yes", "label": "Doğru", "tone": "primary"},
                          {"key": "no", "label": "Yanlış", "tone": "ghost"}, fix])
    elif typ == "proofing":
        title = (it["reason"] or "").split("—", 1)[-1].split(":")[0].strip() or "Son okuma"
        v.update(subject="Son okuma", question=f"Son okuma bulgusu: {title}",
                 statement="Bu bulgu Son Okuma ekranında, gerekçesiyle birlikte karara bağlanır.",
                 link="proofing")
    else:  # fact
        v.update(question="Bu tespit kitaba uyuyor mu?",
                 actions=[{"key": "yes", "label": "Doğru", "tone": "primary"},
                          {"key": "no", "label": "Yanlış", "tone": "ghost"}, fix])
    if v["statement"] is None:
        v["statement"] = "Bu tespit sayfadaki resimden çıkarıldı; karar için resme bakın."
    return v


def _rows(generation_id: str, status: str, limit: int) -> list[dict]:
    return db.all_rows(
        "SELECT r.id, r.priority, r.reason, r.status, r.advisory, r.page_role_page_no, r.proof_run_id,"
        " r.claim_id, r.contradiction_id, c.kind AS claim_kind, c.claim, c.source_pages, c.payload,"
        " x.kind AS contradiction_kind, x.description, x.pages"
        " FROM review_item r LEFT JOIN claim c ON c.id=r.claim_id"
        " LEFT JOIN contradiction x ON x.id=r.contradiction_id"
        " WHERE r.generation_id=%s AND r.status=%s ORDER BY r.priority, r.created_at LIMIT %s",
        generation_id, status, limit)


def _evidence(claim_ids: list) -> tuple[dict, dict]:
    """The book's own sentence for each claim (TEXT evidence only, verified first) and the
    figures a claim rests on (VISUAL evidence: shown as the picture, never as its text)."""
    quotes: dict[str, dict] = {}
    figures: dict[str, list[str]] = {}
    if not claim_ids:
        return quotes, figures
    for e in db.all_rows(
            "SELECT ce.claim_id::text AS claim_id, e.kind, e.quote, e.page_no, e.quote_verified,"
            " e.region_id::text AS region_id FROM claim_evidence ce JOIN evidence e ON e.id=ce.evidence_id"
            " WHERE ce.claim_id::text = ANY(%s) ORDER BY e.quote_verified DESC, e.page_no",
            [str(x) for x in claim_ids]):
        if e["kind"] == "VISUAL" and e["region_id"]:
            figures.setdefault(e["claim_id"], []).append(e["region_id"])
        elif e["kind"] == "TEXT" and e["claim_id"] not in quotes and _turkish(e["quote"]):
            quotes[e["claim_id"]] = {"text": e["quote"].strip(), "page": e["page_no"]}
    return quotes, figures


def queue(book_id: str, status: str = "OPEN", limit: int = 500) -> dict:
    """Open review items of the book's newest generation, grouped by question, each in the
    shape `_view` gives it. The machine note (`reason`) is not part of the answer."""
    gen = _newest_generation(book_id)
    rows = _rows(gen["id"], status, limit)
    quotes, figures = _evidence([r["claim_id"] for r in rows if r["claim_id"]])
    # advice (027_review_advisory): shown, answerable, after the questions, never counted as open
    items = [{**_view(r, quotes.get(str(r["claim_id"])), figures.get(str(r["claim_id"]), [])[:4]),
              "advisory": bool(r["advisory"])} for r in rows]
    groups = []
    for typ in ORDER:
        # In the order the book is read: an editor goes through a group page by page.
        members = sorted((i for i in items if i["type"] == typ),
                         key=lambda i: (i["advisory"], i["pages"][0] if i["pages"] else 10**6, i["priority"]))
        if members:
            groups.append({"type": typ, "title": GROUP[typ][0], "bulk": GROUP[typ][1], "items": members})
    counts = db.all_rows("SELECT status, advisory, count(*) AS n FROM review_item WHERE generation_id=%s"
                         " GROUP BY status, advisory", gen["id"])
    return {"book_id": book_id, "title": gen["title"], "generation_id": gen["id"],
            "groups": groups,
            "open": sum(r["n"] for r in counts if r["status"] == "OPEN" and not r["advisory"]),
            "advice": sum(r["n"] for r in counts if r["status"] == "OPEN" and r["advisory"]),
            "decided": sum(r["n"] for r in counts if r["status"] != "OPEN")}


# --------------------------------------------------------------------------- deciding
# What a button does, per question type. Each effect was checked against what the reading
# actually uses (`usable_claim`: status VERIFIED/EDITOR_APPROVED/EDITOR_CORRECTED and NOT
# needs_editor_review; `knowledge._persist`: a page leaves the story only by a page_role row
# with source='editor'). A decision that changes nothing downstream is not offered.
#   yes/no answer the question shown; «fix» keeps the finding out of this reading and carries
#   the editor's note into the next one (`ledger.corrections_for_book`).

ITEM_STATUS = {"yes": "APPROVED", "no": "REJECTED", "fix": "CORRECTED"}
# The CLI's older words, kept so `editorctl review decide` still works.
LEGACY = {"approve": "yes", "reject": "no", "correct": "fix"}


def _correction(c, it: dict, editor: str, target_kind: str, target_key: str, data: dict) -> None:
    c.execute("INSERT INTO editor_correction(book_id, review_item_id, target_kind, target_key,"
              " correction, editor) VALUES (%s,%s,%s,%s,%s,%s)",
              (it["book_id"], it["id"], target_kind, target_key[:200], db.J(data), editor))


def _claim(c, claim_id, status: str, usable: bool) -> None:
    c.execute("UPDATE claim SET status=%s, needs_editor_review=%s WHERE id=%s",
              (status, not usable, claim_id))


def choose(item_id: str, choice: str, editor: str, note: str | None = None) -> dict:
    """One decision, with the effect its button promised."""
    choice = LEGACY.get(choice, choice)
    if choice not in ITEM_STATUS:
        raise ValueError("Geçersiz seçim.")
    if not (editor or "").strip():
        raise ValueError("Kararı veren kişi belli değil.")
    note = (note or "").strip() or None
    if choice == "fix" and not note:
        raise ValueError("Düzeltme için bir not yazın.")
    with db.tx() as c:
        it = c.execute(
            "SELECT r.*, bv.book_id, c.kind AS claim_kind, c.claim, c.subject, c.payload, c.source_pages,"
            " x.kind AS contradiction_kind, x.description, x.pages"
            " FROM review_item r JOIN generation g ON g.id=r.generation_id"
            " JOIN book_version bv ON bv.id=g.book_version_id"
            " LEFT JOIN claim c ON c.id=r.claim_id LEFT JOIN contradiction x ON x.id=r.contradiction_id"
            " WHERE r.id=%s FOR UPDATE OF r", (item_id,)).fetchone()
        if it is None:
            raise KeyError("Kayıt bulunamadı.")
        if it["status"] != "OPEN":
            raise ValueError("Bu kayıt daha önce karara bağlanmış.")
        typ = _type(it)
        if typ == "proofing":
            raise ValueError("Son okuma bulguları Son Okuma ekranında karara bağlanır.")
        record: dict[str, Any] = {"choice": choice, "type": typ}
        if note:
            record["note"] = note
        key = it["subject"] or (it["claim"] or "")[:200]
        if typ == "page":
            p = it["page_role_page_no"]
            role = "NON_STORY" if choice == "yes" else "STORY"
            if choice == "fix":
                raise ValueError("Sayfa için Evet ya da Hayır seçilir.")
            c.execute("INSERT INTO page_role(generation_id, page_no, role, source) VALUES (%s,%s,%s,'editor')"
                      " ON CONFLICT (generation_id, page_no) DO UPDATE SET role=EXCLUDED.role, source='editor'",
                      (it["generation_id"], p, role))
            _correction(c, it, editor, "PAGE_ROLE", f"s{p}", {"role": role})
            record["role"] = role
        elif typ.startswith("conflict"):
            status = "EDITOR_DISMISSED" if choice == "no" else "EDITOR_CONFIRMED"
            c.execute("UPDATE contradiction SET status=%s WHERE id=%s", (status, it["contradiction_id"]))
            if choice == "fix":
                _correction(c, it, editor, "CONTRADICTION", (it["description"] or "")[:200], {"note": note})
        elif typ == "actor":
            q = _actor_question(it["reason"] or "") or {"direction": None, "names": []}
            # The finding as extracted is right exactly when the reading's doubt is wrong.
            extracted_right = (q["direction"] == "absent" and choice == "yes") or \
                              (q["direction"] == "doer" and choice == "no") or \
                              (q["direction"] is None and choice == "yes")
            if choice == "fix" or not extracted_right:
                _claim(c, it["claim_id"], "EDITOR_CORRECTED", usable=False)
                fix_data = {"note": note} if choice == "fix" else \
                    {"participants": q["names"], "present": q["direction"] == "doer"}
                _correction(c, it, editor, "EVENT_ACTOR", key, fix_data)
                record.update(fix_data)
            else:
                _claim(c, it["claim_id"], "EDITOR_APPROVED", usable=True)
        elif typ == "modality":
            if choice == "yes":
                _claim(c, it["claim_id"], "EDITOR_APPROVED", usable=True)
            else:
                modality = (it["payload"] or {}).get("modality") or "REALIZED"
                _claim(c, it["claim_id"], "EDITOR_CORRECTED", usable=False)
                _correction(c, it, editor, "EVENT_MODALITY", key,
                            {"note": note} if note else {"not": modality})
        else:  # fact, identity
            if choice == "yes":
                _claim(c, it["claim_id"], "EDITOR_APPROVED", usable=True)
            elif choice == "no":
                _claim(c, it["claim_id"], "EDITOR_REJECTED", usable=False)
            else:
                _claim(c, it["claim_id"], "EDITOR_CORRECTED", usable=False)
                _correction(c, it, editor, it["claim_kind"] or "CLAIM", key, {"note": note})
        c.execute("UPDATE review_item SET status=%s, decided_by=%s, decision=%s, decided_at=now() WHERE id=%s",
                  (ITEM_STATUS[choice], editor, db.J(record), item_id))
    return {"item": item_id, "status": ITEM_STATUS[choice], "decided_by": editor, "type": typ}


def decide(item_id: str, decision: str, editor: str, data: dict | None = None) -> dict:
    """The CLI's entry point: approve/reject/correct, with the correction's text as the note."""
    note = (data or {}).get("note") or (json.dumps(data, ensure_ascii=False) if data else None)
    return choose(item_id, decision, editor, note)


def decide_many(book_id: str, item_ids: list[str], choice: str, editor: str,
                note: str | None = None) -> dict:
    """One answer for several items of one book — «these thirteen pages are all front matter»
    is one judgement, not thirteen. Each item is still decided on its own row with its own
    effect, so nothing is closed in bulk without a trace; an item that cannot be decided
    (already closed, not this book's, a proofing finding) is reported, not skipped."""
    choice = LEGACY.get(choice, choice)
    if choice not in ITEM_STATUS:
        raise ValueError("Geçersiz seçim.")
    if not (editor or "").strip():
        raise ValueError("Kararı veren kişi belli değil.")
    if choice == "fix" and not (note or "").strip():
        raise ValueError("Düzeltme için bir not yazın.")
    gen = _newest_generation(book_id)
    mine = {str(r["id"]) for r in db.all_rows(
        "SELECT id FROM review_item WHERE generation_id=%s AND status='OPEN'", gen["id"])}
    done, failed = [], []
    for item_id in item_ids:
        if item_id not in mine:
            failed.append({"item": item_id, "error": "bu kitabın açık kaydı değil"})
            continue
        try:
            done.append(choose(item_id, choice, editor, note))
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
        raise KeyError("Sayfa bulunamadı.")
    existing = Path(row["render_path"]) if row["render_path"] else None
    if existing and existing.exists():
        return existing
    try:
        return Path(render_page(gen["book_version_id"], page_no)["path"])
    except OSError as e:      # read-only storage and the render was never made
        raise KeyError("Sayfanın görüntüsü yok.") from None


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
        raise KeyError("Görsel bulunamadı.")
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
