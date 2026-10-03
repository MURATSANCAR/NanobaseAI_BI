"""book_knowledge tools: characters, identities, events, emotions, themes,
timeline and contradiction candidates. All writes carry evidence.

Chunk extraction runs as a small LangGraph graph (extract -> verify quotes ->
repair once if too many quotes are not found in the page text -> persist)."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from . import budget, db, ledger, naming, prompts, schemas, source
from .config import settings
from .document import page_text_numbered
from .llm import Llm

DIRECTOR = "book-director"
_HEADING = re.compile(r"^[A-ZÇĞİÖŞÜ0-9 ,.'’!?-]{6,60}$")


# ------------------------------------------------- shared model capacity
def director_capacity() -> int:
    """How many director requests the model serves at once: EDITOR_DIRECTOR_CONCURRENCY if set,
    else the director's own `--max-num-seqs` in models.yaml, else EDITOR_PAGE_CONCURRENCY. This
    is the model's capacity, not a cap on books or work: everything still runs, only in turn."""
    import os
    raw = os.environ.get("EDITOR_DIRECTOR_CONCURRENCY", "").strip()
    if raw:
        return max(1, int(raw))
    try:
        import yaml
        spec = yaml.safe_load(settings().models_yaml.read_text())
        for arg in ((spec.get("aliases") or {}).get(DIRECTOR) or {}).get("args") or []:
            m = re.fullmatch(r"--max-num-seqs[= ](\d+)", str(arg).strip())
            if m:
                return max(1, int(m.group(1)))
    except Exception:  # noqa: BLE001 - no readable manifest: fall back to the page setting
        pass
    return max(1, settings().page_concurrency)


_director_slots: dict[int, tuple[Any, asyncio.Semaphore]] = {}


def director_slots() -> asyncio.Semaphore:
    """One semaphore per event loop, shared by every book this worker process reads at the same
    time. Measured 2026-10-02: one book's critic sent 1.115 repair calls at once; 48 activities
    doing that together queued thousands of requests behind a model that serves 32. Waiting here
    costs nothing; waiting inside the model's queue holds the worker's sockets and memory."""
    loop = asyncio.get_running_loop()
    held = _director_slots.get(id(loop))
    if held is None or held[0] is not loop:
        held = (loop, asyncio.Semaphore(director_capacity()))
        _director_slots[id(loop)] = held
    return held[1]


# --------------------------------------------------------------- chapters
def chapters(generation_id: str) -> list[dict]:
    """Chapters from the book's own typesetting (`editor.chapters`: point size, sunk chapter
    openings, title pages). Without the PDF, upper-case headings at the top of a page that is
    followed by body text on the same page (`chapters_from_pages`)."""
    from . import chapters as typeset
    pages = source.read(generation_id)
    return typeset.for_generation(generation_id, pages) or chapters_from_pages(pages)


def chapters_from_pages(pages: list[dict]) -> list[dict]:
    """Pure chapter proposal over an already captured source snapshot."""
    rows = [{"page_no":p["page_no"],**span} for p in pages for span in source.body_spans(p)]
    last_page = max((p["page_no"] for p in pages), default=0)
    by_page: dict[int, list[str]] = {}
    for r in rows:
        by_page.setdefault(r["page_no"], []).append(r["text"].strip())
    starts = []
    for p, paras in sorted(by_page.items()):
        head = []
        for t in paras:
            if _HEADING.match(t) and t.upper() == t and not t.isdigit():
                head.append(t)
            else:
                break
        # a chapter heading is followed directly by story text: a long paragraph
        # that ends like a sentence (title pages and imprint lines are not)
        nxt = paras[len(head)] if len(paras) > len(head) else ""
        if head and len(nxt) > 60 and nxt.rstrip()[-1:] in ".!?”\"…" and len(" ".join(head).split()) >= 2:
            starts.append((p, " ".join(head)))
    if not starts:
        return [{"title": "Kitap", "page_from": 1, "page_to": last_page}]
    out = []
    for i, (p, title) in enumerate(starts):
        end = starts[i + 1][0] - 1 if i + 1 < len(starts) else last_page
        out.append({"title": title, "page_from": p, "page_to": max(p, end)})
    if starts[0][0] > 1:
        out.insert(0, {"title": "Başlıksız başlangıç", "page_from": 1, "page_to": starts[0][0] - 1})
    return out


def corrections_text(generation_id: str) -> str:
    rows = db.all_rows("SELECT corrections_applied FROM generation WHERE id=%s", generation_id)
    items = rows[0]["corrections_applied"] if rows else []
    return "\n".join(f"- {c['target_kind']} / {c['target_key']}: "
                     f"{json.dumps(c['correction'], ensure_ascii=False)}" for c in items) or "-"


def _valid_pages(c, generation_id: str) -> set[int]:
    return {r["page_no"] for r in c.execute(
        "SELECT p.page_no FROM page p JOIN generation g ON g.book_version_id=p.book_version_id "
        "WHERE g.id=%s", (generation_id,))}


# ------------------------------------------------------ chunk extraction
class ChunkState(TypedDict, total=False):
    generation_id: str
    page_from: int
    page_to: int
    body: str
    ref: Any
    out: dict
    call_id: int
    unverified: list[str]
    attempts: int
    persisted: dict


def _visual_summary(generation_id: str, a: int, b: int) -> str:
    lines = []
    for r in db.all_rows("SELECT DISTINCT ON (page_no) page_no, result FROM page_scan WHERE "
                         "generation_id=%s AND page_no BETWEEN %s AND %s ORDER BY page_no,"
                         " (pass='DEEP') DESC", generation_id, a, b):
        res = r["result"]
        # In a picture with several figures the scan's names are guesses (they are settled
        # later by reference images), so the extractor only gets names it can rely on.
        solo = len(res["characters"]) == 1
        chars = "; ".join(f"{(c['name'] if solo and not c['identity_uncertain'] else '') or c['label']}"
                          f": {c['action']}" for c in res["characters"])
        lines.append(f"[s{r['page_no']}] Sahne: {res['scene']['description']} | Karakterler: {chars}")
    return "\n".join(lines) or "-"


async def _extract(st: ChunkState) -> ChunkState:
    gid, a, b = st["generation_id"], st["page_from"], st["page_to"]
    if "body" not in st:
        # Page text, visual summary and corrections are database reads: off the event loop.
        def render() -> tuple:
            text = "\n".join(page_text_numbered(gid, p) for p in range(a, b + 1))
            return prompts.render("extract_knowledge", page_from=str(a), page_to=str(b),
                                  pages_text=text, visual_summary=_visual_summary(gid, a, b),
                                  corrections=corrections_text(gid))
        ref, body = await asyncio.to_thread(render)
        st = {**st, "body": body, "ref": ref}
    messages = [{"role": "user", "content": st["body"]}]
    if st.get("unverified"):
        messages += [{"role": "assistant", "content": json.dumps(st["out"], ensure_ascii=False)},
                     {"role": "user", "content": "Şu alıntılar sayfa metninde birebir bulunamadı; "
                      "her birini metinden KELİMESİ KELİMESİNE alınmış bir parçayla değiştir ya da "
                      "o öğeyi çıkar. Tüm çıktıyı yeniden ver:\n" + "\n".join(st["unverified"][:40])}]
    out, call_id = await Llm(gid).chat(DIRECTOR, messages, prompt=st["ref"],
                                       schema=schemas.KNOWLEDGE, pages=list(range(a, b + 1)),
                                       max_tokens=12000, temperature=0.1, thinking=False)
    return {**st, "out": out, "call_id": call_id, "attempts": st.get("attempts", 0) + 1}


def _verify(st: ChunkState) -> ChunkState:
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, st["generation_id"])
    bad, total = [], 0
    o = st["out"]
    for item in o["character_mentions"] + o["events"] + o["emotions"] + o["themes"]:
        for e in item["evidence"]:
            total += 1
            if int(e.get("paragraph") or 0) > 0 and not idx.verify(int(e["page"]), e["quote"], "TEXT", int(e["paragraph"])):
                bad.append(f"s{e['page']}: “{e['quote']}”")
    return {**st, "unverified": bad if total and len(bad) / total > 0.2 else []}


def _route(st: ChunkState) -> str:
    return "extract" if st.get("unverified") and st.get("attempts", 0) < 2 else "persist"


def _persist(st: ChunkState) -> ChunkState:
    gid, o, call_id = st["generation_id"], st["out"], st["call_id"]
    counts = {"mentions": 0, "events": 0, "emotions": 0, "themes": 0, "dropped_no_evidence": 0,
              "dropped_non_story": 0, "credits": 0, "credit_people": []}
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, gid)
        pages = _valid_pages(c, gid)
        suggested_non_story = {p for p in o.get("non_story_pages", []) if st["page_from"] <= p <= st["page_to"]}
        for p in suggested_non_story:
            c.execute("INSERT INTO page_role(generation_id, page_no, role, source, model_call_id)"
                      " VALUES (%s,%s,'NON_STORY','extract',%s) ON CONFLICT DO NOTHING", (gid, p, call_id))
            ledger.queue_review(c,gid,reason=f"Sayfa türü incelemesi: s{p}; çıkarıcının NON_STORY önerisi, kapsamdan çıkarılmadı",priority=2,page_role_page_no=p)
        # The suggestion alone never removes a page (non-fiction bodies get it wholesale). A page whose
        # TEXT is the imprint, title page, author bio, contents or the publisher's adverts is out of the
        # book at once, in both profiles, without waiting for an editor (editor.page_scope; the
        # editor can turn it back): nothing is extracted from it.
        from . import page_scope
        page_scope.for_chunk(c, gid, st["page_from"], st["page_to"], suggested_non_story)
        non_story = {r["page_no"] for r in c.execute("SELECT page_no FROM page_role WHERE generation_id=%s "
            "AND source = ANY(%s) AND role IN ('FRONT_MATTER','NON_STORY')",(gid, list(page_scope.SCOPE_SOURCES)))}

        def story(item: dict, *keys: str) -> bool:
            """Keep an item only if none of its pages is a non-story page."""
            ps = {int(item[k]) for k in keys if item.get(k)} | {int(e["page"]) for e in item["evidence"]}
            if ps & non_story:
                counts["dropped_non_story"] += 1
                return False
            return True

        o = {**o, "character_mentions": [m for m in o["character_mentions"] if story(m, "page")],
             "events": [e for e in o["events"] if story(e, "page_from", "page_to")],
             "emotions": [e for e in o["emotions"] if story(e, "page")],
             "themes": [t for t in o["themes"] if story(t)]}
        last_page = max(pages) if pages else 0
        for m in o["character_mentions"]:
            # a name printed as the book's credit (imprint) is not a person of the text
            role = naming.credit_role(m["surface_name"], " ".join(e["quote"] for e in m["evidence"]),
                                      m.get("page"), last_page)
            if role:
                counts["credits"] += 1
                counts["credit_people"].append({"name": m["surface_name"], "role": role, "page": m.get("page")})
                continue
            evs = ledger.evidence_from_model(c, gid, idx, m["evidence"], valid_pages=pages)
            if not evs:
                counts["dropped_no_evidence"] += 1
                continue
            c.execute("INSERT INTO character_mention(generation_id, page_no, surface_name, via,"
                      " appearance, resolution, confidence, evidence_id) VALUES"
                      " (%s,%s,%s,%s,%s,'UNRESOLVED',%s,%s)",
                      (gid, m["page"] if m["page"] in pages else evs[0][2], m["surface_name"],
                       # the extractor works from text; only a page scan can see a figure
                       "TEXT", db.J({"description": m["description"]}), m["confidence"], evs[0][0]))
            counts["mentions"] += 1
        for ev in o["events"]:
            evs = ledger.evidence_from_model(c, gid, idx, ev["evidence"], valid_pages=pages)
            if not evs:
                counts["dropped_no_evidence"] += 1
                continue
            conf = ev["confidence"] * (1.0 if any(ok for _, ok, _ in evs) else 0.5)
            cid = ledger.save_claim(c, gid, kind="EVENT", subject=", ".join(ev["participants"]),
                                    claim=ev["summary"], evidence=evs, confidence=conf,
                                    created_by="knowledge:extract", model_call_id=call_id,
                                    payload={"modality": ev["modality"]})
            pf, pt = sorted((ev["page_from"], ev["page_to"]))
            c.execute("INSERT INTO event(generation_id, page_from, page_to, summary, modality,"
                      " participants, importance, confidence, claim_id) VALUES"
                      " (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                      (gid, pf, pt, ev["summary"], ev["modality"], ev["participants"],
                       ev["importance"], conf, cid))
            counts["events"] += 1
        for em in o["emotions"]:
            evs = ledger.evidence_from_model(c, gid, idx, em["evidence"], valid_pages=pages)
            if not evs:
                counts["dropped_no_evidence"] += 1
                continue
            cid = ledger.save_claim(c, gid, kind="EMOTION", subject=em["character"],
                                    claim=f"{em['character']} {em['emotion']} hissediyor"
                                          + (f" ({em['trigger']})" if em["trigger"] else ""),
                                    evidence=evs, confidence=em["confidence"],
                                    created_by="knowledge:extract", model_call_id=call_id,
                                    payload={"emotion": em["emotion"], "intensity": em["intensity"],
                                             "trigger": em["trigger"]})
            c.execute("INSERT INTO emotion(generation_id, character_name, page_no, emotion,"
                      " intensity, trigger, confidence, claim_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                      (gid, em["character"], em["page"] if em["page"] in pages else evs[0][2],
                       em["emotion"], em["intensity"], em["trigger"], em["confidence"], cid))
            counts["emotions"] += 1
        for th in o["themes"]:
            evs = ledger.evidence_from_model(c, gid, idx, th["evidence"], valid_pages=pages)
            if not evs:
                counts["dropped_no_evidence"] += 1
                continue
            ledger.save_claim(c, gid, kind="THEME", subject="bölüm teması", claim=th["theme"],
                              evidence=evs, confidence=th["confidence"],
                              created_by="knowledge:extract", model_call_id=call_id,
                              payload={"level": "chunk", "pages": [st["page_from"], st["page_to"]]})
            counts["themes"] += 1
    return {**st, "persisted": counts}


def _graph():
    g = StateGraph(ChunkState)
    g.add_node("extract", _extract)
    g.add_node("verify", _verify)
    g.add_node("persist", _persist)
    g.add_edge(START, "extract")
    g.add_edge("extract", "verify")
    g.add_conditional_edges("verify", _route, {"extract": "extract", "persist": "persist"})
    g.add_edge("persist", END)
    return g.compile()


_GRAPH = _graph()


async def extract_chunk(generation_id: str, page_from: int, page_to: int) -> dict:
    st = await _GRAPH.ainvoke({"generation_id": generation_id, "page_from": page_from,
                               "page_to": page_to})
    return {"pages": [page_from, page_to], "attempts": st["attempts"], **st["persisted"],
            "unverified_left": len(st.get("unverified") or [])}


def text_chunks(generation_id: str, size: int = 4) -> list[tuple[int, int]]:
    """All physical pages; chapter discovery never decides source coverage.

    Missing text and visual-only pages remain scheduled and visible to coverage.
    This function is read-only, including on legacy sealed generations.
    """
    if size < 1:
        raise ValueError("chunk size must be positive")
    pages = [r["page_no"] for r in db.all_rows("SELECT p.page_no FROM page p JOIN generation g "
        "ON g.book_version_id=p.book_version_id WHERE g.id=%s ORDER BY p.page_no",generation_id)]
    return [(pages[i], pages[min(i + size, len(pages)) - 1]) for i in range(0, len(pages), size)]





def _emotion_character(c, generation_id: str, name: str, page: int, claim_id: str):
    """A name narrows candidates; a shared verified source span establishes locality.

    Never bind a person from aliases alone or choose an arbitrary first match.
    Missing/ambiguous provenance remains unlinked, including historical evidence.
    """
    evidence = c.execute(
        "SELECT e.source_refs FROM claim_evidence ce JOIN evidence e ON e.id=ce.evidence_id "
        "JOIN claim cl ON cl.id=ce.claim_id AND cl.generation_id=e.generation_id "
        "WHERE ce.claim_id=%s AND e.generation_id=%s AND e.page_no=%s "
        "AND e.kind='TEXT' AND e.quote_verified "
        "AND cl.status NOT IN ('REJECTED','EDITOR_REJECTED','SUPERSEDED')",
        (claim_id, generation_id, page)).fetchall()

    def spans(refs):
        refs = refs or {}
        if str(refs.get('generation_id')) != str(generation_id) or refs.get('page_no') != page:
            return set()
        return {(r['span_id'], r['source_sha256']) for r in refs.get('spans', [])
                if r.get('span_id') and r.get('source_sha256')}

    supporting = set().union(*(spans(e['source_refs']) for e in evidence))
    if not supporting:
        return None
    mentions = c.execute(
        "SELECT ch.id,ch.canonical_name,ch.aliases,cm.surface_name,e.source_refs "
        "FROM character_mention cm JOIN character ch ON ch.id=cm.character_id "
        "AND ch.generation_id=cm.generation_id JOIN evidence e ON e.id=cm.evidence_id "
        "AND e.generation_id=cm.generation_id JOIN claim cl ON cl.id=ch.claim_id "
        "AND cl.generation_id=ch.generation_id WHERE cm.generation_id=%s AND cm.page_no=%s "
        "AND e.page_no=cm.page_no AND cm.resolution='RESOLVED' "
        "AND ch.identity_status='CONFIRMED' AND ch.traits->>'entity_scope'='INDIVIDUAL' "
        "AND e.kind='TEXT' AND e.quote_verified "
        "AND cl.status NOT IN ('REJECTED','EDITOR_REJECTED','SUPERSEDED')",
        (generation_id, page)).fetchall()
    target = ledger.norm(name)
    candidates = {m['id'] for m in mentions if target and target in
        {ledger.norm(n) for n in [m['canonical_name'], *(m['aliases'] or []), m['surface_name']] if n}
        and supporting & spans(m['source_refs'])}
    return next(iter(candidates)) if len(candidates) == 1 else None


# ------------------------------------------------------ identity merge
def _identity_error_is_deterministic(e: BaseException) -> bool:
    """Would the same identity request fail the same way again? A request larger than the
    context, an answer that runs out of room, a model answer that breaks the partition contract
    three times, a window plan with no room: yes — retrying the activity only repeats it (the
    2026-09-23/24 failures were four identical 400s per book). A busy card or a dropped
    connection: no — the activity retry is the right answer to those."""
    from .llm import ContextOverflow, ModelError
    if isinstance(e, (ContextOverflow, ValueError)):          # BudgetError, JSONDecodeError too
        return True
    if isinstance(e, ModelError):
        text = str(e)
        return "gpu_busy" not in text and ("finish_reason=length" in text or ": 400 " in text
                                           or text.startswith("400 ") or "context length" in text.lower())
    return False


# Each fallback halves the reading window: 1/2, then 1/4 of the budget and of the mentions a
# window may carry. Measured sizes are what the budget already reads; this only answers "the
# estimate was not enough" (a critic call, a reconciliation, an answer longer than expected).
IDENTITY_FALLBACK_SHRINKS = (1, 2)


async def _propose_identity(generation_id: str, ms: list[dict], corrections: str,
                            final_attempt: bool) -> tuple[dict | None, int | None, dict]:
    """identity.propose_book, and when it cannot finish, the same over smaller windows. Returns
    (None, None, audit) when no reading produced a partition: the caller then leaves every mention
    unresolved and puts the book in front of the editor, instead of ending the whole reading.
    A transient failure is re-raised for the activity retry, except on its final attempt."""
    from . import identity
    tried: list[dict] = []
    for shrink in (0, *IDENTITY_FALLBACK_SHRINKS):
        try:
            out, call_id, audit = await identity.propose_book(generation_id, ms, corrections, shrink=shrink)
        except Exception as e:  # noqa: BLE001 - classified below; nothing is swallowed silently
            if not (_identity_error_is_deterministic(e) or final_attempt):
                raise
            tried.append({"shrink": shrink, "error": f"{type(e).__name__}: {str(e)[:600]}"})
            continue
        if tried:
            audit = {**audit, "fallback": tried}
        return out, call_id, audit
    return None, None, {"policy": identity.POLICY, "failed": True, "fallback": tried}


def _identity_unresolved(generation_id: str, ms: list[dict], audit: dict) -> dict:
    """No partition could be read: the mentions stay unresolved (as they already are), and one
    CHARACTER_IDENTITY question goes to the editor's queue with the reason, citing the book's own
    mention quotes. The reading goes on; the book cannot be accepted while the question is open
    (OPEN_EDITOR_REVIEW)."""
    reason = "; ".join(t["error"] for t in audit.get("fallback", []))[:1500] or "bilinmeyen"
    with db.tx() as c:
        evs, seen = [], set()
        for m in ms:
            if m["page_no"] in seen:
                continue
            e = c.execute("SELECT evidence_id FROM character_mention WHERE id=%s", (m["id"],)).fetchone()
            if e:
                seen.add(m["page_no"])
                evs.append((str(e["evidence_id"]), True, m["page_no"]))
            if len(evs) >= 8:
                break
        cid = ledger.save_claim(
            c, generation_id, kind="CHARACTER_IDENTITY", subject="Karakter kimlikleri",
            claim=f"Karakter kimlikleri otomatik birleştirilemedi; {len(ms)} karakter anması çözülmeden "
                  "bırakıldı. Kişiler editör incelemesiyle belirlenmeli.",
            evidence=evs, confidence=0.0, created_by="knowledge:identity",
            payload={"identity_failed": True, "identity_audit": audit})
        if cid:
            ledger.queue_review(c, generation_id, claim_id=cid, priority=1,
                                reason=f"Karakter kimliği birleştirilemedi: {len(ms)} anma çözülmedi ({reason})")
    return {"characters": 0, "confirmed": 0, "unresolved_mentions": len(ms), "conflicts": 0,
            "names_refused": 0, "entities_refused": [], "list": [], "identity_failed": True,
            "review_queued": bool(cid), "identity_audit": audit}


def identity_unresolved(generation_id: str, error: str) -> dict:
    """The workflow's last resort when the identity activity itself could not finish (a timeout,
    a crash after every retry): the same editor question as `_identity_unresolved`, over the
    mentions that are still unresolved."""
    ms = db.all_rows(
        "SELECT cm.id, cm.page_no FROM character_mention cm WHERE cm.generation_id=%s"
        " AND cm.character_id IS NULL AND cm.via IN ('TEXT','BOTH') ORDER BY cm.page_no, cm.id",
        generation_id)
    if not ms:
        return {"characters": 0, "identity_failed": True, "unresolved_mentions": 0, "review_queued": False}
    return _identity_unresolved(generation_id, ms, {"failed": True, "fallback": [{"error": error[:1500]}]})


def _book_contributors(c, generation_id: str) -> list[str]:
    """Authors and illustrators from the publisher's CRM record, when the book has one."""
    if not c.execute("SELECT to_regclass('ed.book_crm_record') AS t").fetchone()["t"]:
        return []
    r = c.execute("SELECT r.authors, r.illustrators FROM book_crm_record r JOIN book_version bv"
                  " ON bv.book_id=r.book_id JOIN generation g ON g.book_version_id=bv.id WHERE g.id=%s",
                  (generation_id,)).fetchone()
    if not r:
        return []
    return [str(x) for x in list(r["authors"] or []) + list(r["illustrators"] or []) if x]


async def resolve_character_identity(generation_id: str, final_attempt: bool = False) -> dict:
    """Names are resolved from the TEXT only. The model groups text mentions; the
    alias list is not the model's to write: it is exactly the set of names under
    which the merged mentions occur in the book, so a figure label or a note can
    never become an alias. Appearance is not part of identity here; drawn figures are
    attached afterwards by reference images (vision.resolve_visual_identity).
    CONFIRMED needs >= 0.85 and evidence on at least two pages.

    Three invariants are enforced here, where the record is accepted, not later on a
    screen (editor.naming measures them over the book's own text):
      * a collective or a concept does not become a person: no character row, its
        mentions stay unresolved;
      * an alias must be written the way the book writes a name (capitalised in the
        middle of a sentence), so a pronoun or a common noun cannot become a second name;
      * an alias cannot be another character's canonical name in this generation;
      * an alias written with no other name of the character on any page of the book has
        nothing in the book that joins the two names (naming.screen_shared_evidence).
    A refused name does not just disappear from the list: the mentions that carried it
    are exactly the ones that pointed at the wrong person, so they go back to unresolved
    instead of staying attached to this character.

    A person whose every mention is on a page about the book rather than in it (an author's
    or illustrator's note, a title page — naming.paratext_pages) is not written as a character.

    `first_page` stays the page a character is first named on; the pages its DESCRIPTION rests
    on are chosen separately (naming.description_pages) and stored as traits.description_pages,
    first in the identity claim's evidence — a cast page that prints only names is not the
    source of what the description says.

    When no proposal can be read at all (every fallback of `_propose_identity` failed) the
    mentions stay unresolved, the editor gets one question, and the reading goes on."""
    ms = db.all_rows(
        "SELECT cm.id, cm.page_no, cm.surface_name, cm.confidence, e.quote FROM character_mention cm"
        " JOIN evidence e ON e.id=cm.evidence_id WHERE cm.generation_id=%s AND cm.character_id IS NULL"
        " AND cm.via IN ('TEXT','BOTH') AND e.kind='TEXT' AND e.quote_verified "
        "AND e.generation_id=cm.generation_id AND cm.surface_name IS NOT NULL ORDER BY cm.page_no,cm.id",
        generation_id)
    if not ms:
        return {"characters": 0}
    short = {str(m["id"]): f"m{i}" for i, m in enumerate(ms)}
    back = {v: k for k, v in short.items()}
    # any length: one call when the book fits, else window by window (identity.propose_book);
    # smaller windows when that cannot finish; the editor's queue when nothing can
    out, call_id, audit = await _propose_identity(generation_id, ms, corrections_text(generation_id),
                                                  final_attempt)
    if out is None:
        return _identity_unresolved(generation_id, ms, audit)
    # a windowed audit lists every window; each claim keeps a short form and its own windows
    claim_audit = audit if not audit.get("windowed") else {
        k: audit[k] for k in ("policy", "windowed", "mentions_unresolved") if k in audit} | {
        "windows": len(audit.get("windows", [])), "windows_failed": len(audit.get("failed", []))}
    by_id = {str(m['id']): m for m in ms}
    conflicted = {back[x['mention_id']] for x in out['conflicts']}
    # Proposal is an exact partition. Same surface names never override identity evidence.
    groups = {gi: [back[x] for x in ch['mention_ids']] for gi,ch in enumerate(out['characters'])}
    claimed: set[str] = set()
    made = []
    refused: list[dict] = []
    loosened: set[str] = set()      # mentions a refused name or a refused entity gave back
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)
        source_text = " ".join(idx.text.values())
        # the book as it is written: capitalisation is the measurement, so the raw spans
        # are read here and not the normalised index
        written_text = "\n".join(idx.raw[p] for p in sorted(idx.raw))
        # ---- first pass: what the book calls each proposed character
        plans: list[dict] = []
        for gi, ch in enumerate(out["characters"]):
            mids = [m for m in dict.fromkeys(groups[gi]) if m not in claimed]
            if not mids:
                continue
            claimed.update(mids)
            # the names this character carries in the book, most frequent first
            counts: dict[str, list] = {}
            for m in mids:
                n = by_id[m]["surface_name"].strip()
                counts.setdefault(ledger.norm(n), [n, 0])[1] += 1
            names = [v[0] for v in sorted(counts.values(), key=lambda v: -v[1])]
            canonical = ch["canonical_name"].strip()
            if ledger.norm(canonical) not in counts:        # the model may not invent a name
                canonical = names[0]
            attested = [n for n in names if ledger.has_name(source_text, n, allow_suffix=True)]
            labels = [n for n in names if n not in attested]
            if canonical not in attested and attested:
                canonical = attested[0]
            aliases = [n for n in attested if ledger.norm(n) != ledger.norm(canonical)]
            name_origin = "SOURCE_TEXT" if canonical in attested else "DESCRIPTIVE_LABEL"
            plans.append({"ch": ch, "mids": mids, "canonical": canonical, "aliases": aliases,
                          "labels": labels, "name_origin": name_origin,
                          "entity_scope": ch.get("entity_scope") or "UNKNOWN"})
        # ---- name invariants, over the whole proposal at once
        st = settings()
        verdicts = naming.screen_group_names(
            [{k: p[k] for k in ("canonical", "aliases", "entity_scope")} for p in plans],
            written_text, min_share=st.proper_name_min_share, min_uses=st.proper_name_min_uses)
        # two written names are one person only where the book joins them
        verdicts = naming.screen_shared_evidence(verdicts, idx.raw)
        # ---- pages about the book, not in it (author/illustrator notes, title pages)
        role_pages = naming.about_the_book_pages(c.execute(
            "SELECT page_no, role FROM page_role WHERE generation_id=%s", (generation_id,)).fetchall())
        last_page = max(idx.raw) if idx.raw else 0
        paratext = naming.paratext_pages(idx.raw, role_pages, _book_contributors(c, generation_id), last_page)
        # the characters' names say WHO; none of them says what a description says (a relation
        # word a mention was called by — «torunu» — is left in: it is part of the description)
        name_words = {w for v in verdicts if v["person"] for n in (v["canonical"], *v["aliases"])
                      for w in naming.words(n)}
        # ---- second pass: write the characters that survived, with the names that survived
        for plan, verdict in zip(plans, verdicts):
            ch, mids = plan["ch"], plan["mids"]
            named_on = {by_id[m]["page_no"] for m in mids}
            if verdict["person"] and (named_on <= paratext or (
                    ch.get("book_role") == "ABOUT_THE_BOOK"
                    and all(naming.edge_page(p, last_page) for p in named_on))):
                # named only where the book talks about itself: its maker, or the maker's dog.
                # The reader's ABOUT_THE_BOOK alone is not enough: the person must also be named
                # nowhere but the book's first or last pages, so a story person it misread stays.
                verdict = {**verdict, "person": False, "reject_reason": naming.PARATEXT_ONLY}
            if not verdict["person"]:
                # Not a person: no character row at all, so nothing — a drawing, an event
                # actor, a graph edge — can be attached to it later. The mentions and their
                # evidence stay, unresolved, and `coverage` reports them.
                for m in mids:
                    c.execute("UPDATE character_mention SET character_id=NULL,"
                              " resolution='UNRESOLVED' WHERE id=%s", (m,))
                loosened.update(mids)
                refused.append({"name": plan["canonical"], "reason": verdict["reject_reason"],
                                "entity_scope": plan["entity_scope"], "mentions": len(mids),
                                "pages": sorted({by_id[m]["page_no"] for m in mids})[:12]})
                continue
            aliases = verdict["aliases"]
            dropped_keys = {naming.key(d["name"]) for d in verdict["dropped"]}
            # a mention that called this character by a refused name never belonged to it
            loose = [m for m in mids if ledger.norm(by_id[m]["surface_name"]) in dropped_keys]
            mids = [m for m in mids if m not in set(loose)]
            for m in loose:
                c.execute("UPDATE character_mention SET character_id=NULL,"
                          " resolution='UNRESOLVED' WHERE id=%s", (m,))
            loosened.update(loose)
            if not mids:                    # nothing left that this character was called by
                refused.append({"name": plan["canonical"], "reason": "NO_MENTION_LEFT",
                                "entity_scope": plan["entity_scope"], "mentions": len(loose)})
                continue
            canonical, labels, name_origin = plan["canonical"], plan["labels"], plan["name_origin"]
            pages = sorted({by_id[m]["page_no"] for m in mids})
            conf = float(ch["identity_confidence"])
            # One page can explicitly identify a person; keep the independent
            # identity audit and conflict checks, without a page-count veto.
            status = "CONFIRMED" if conf >= 0.85 and ch["entity_scope"] == "INDIVIDUAL" and not (set(mids) & conflicted) else "CANDIDATE"
            # where the description is written, apart from where the name first appears
            desc_pages = naming.description_pages(ch.get("description") or "", idx.raw, pages, name_words)
            # The claim states the description, so it cites the pages the description rests on;
            # without such pages, the first mentions as before. Every mention stays linked to the
            # character either way (character_mention), first_page included.
            rank = {p: i for i, p in enumerate(desc_pages)}
            cited = sorted((m for m in mids if by_id[m]["page_no"] in rank) if rank else mids,
                           key=lambda m: (rank.get(by_id[m]["page_no"], 0), by_id[m]["page_no"]))
            evs = []
            for m in cited[:8]:
                e = c.execute("SELECT evidence_id FROM character_mention WHERE id=%s", (m,)).fetchone()
                evs.append((str(e["evidence_id"]), True, by_id[m]["page_no"]))
            cid = ledger.save_claim(
                c, generation_id, kind="CHARACTER_IDENTITY", subject=canonical,
                claim=canonical + (f" (diğer adlar: {', '.join(aliases)})" if aliases else "")
                + f": {ch['description']}",
                evidence=evs, confidence=conf, created_by="knowledge:identity", model_call_id=call_id,
                payload={"merge_basis": ch["merge_basis"], "aliases": aliases, "identity_status": status,
                         "identity_audit": claim_audit, "names_refused": verdict["dropped"],
                         "first_page": pages[0], "description_pages": desc_pages,
                         **({"windows": ch["windows"]} if ch.get("windows") else {})})
            row = c.execute(
                "INSERT INTO character(generation_id, canonical_name, aliases, description,"
                " identity_status, identity_confidence, first_page, claim_id, kind, traits) VALUES"
                " (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (generation_id, canonical, aliases, ch["description"], status, conf, pages[0], cid,
                 ch.get("kind") or "UNKNOWN",
                 db.J({**{k: ch.get(k) or "UNKNOWN" for k in ("sex", "age_band", "entity_scope")},
                       "name_origin": name_origin, "descriptive_labels": labels,
                       "names_refused": verdict["dropped"], "description_pages": desc_pages}))).fetchone()
            for m in mids:
                sure = float(by_id[m]["confidence"]) >= 0.75 and conf >= 0.75 and m not in conflicted
                c.execute("UPDATE character_mention SET character_id=%s, resolution=%s WHERE id=%s",
                          (row["id"], "RESOLVED" if sure else "UNCERTAIN", m))
            made.append({"name": canonical, "aliases": aliases, "status": status, "confidence": conf,
                         "pages": pages[:12], "description_pages": desc_pages,
                         "names_refused": verdict["dropped"]})
            if status != "CONFIRMED" and len(pages) >= 3 and cid:
                ledger.queue_review(c, generation_id, claim_id=cid, priority=2,
                                    reason=f"Karakter kimliği kesinleşmedi ({conf:.2f}): "
                                           f"{canonical} — {ch['merge_basis']}")
        for m in conflicted - loosened:      # a name given back is not merely uncertain
            c.execute("UPDATE character_mention SET resolution='UNCERTAIN' WHERE id=%s", (m,))
    return {"characters": len(made), "confirmed": sum(1 for m in made if m["status"] == "CONFIRMED"),
            "unresolved_mentions": len(ms) - len(claimed) + len(loosened),
            "conflicts": len(out["conflicts"]),
            "names_refused": sum(len(m["names_refused"]) for m in made),
            "entities_refused": refused,
            "list": made, "identity_audit": audit}


# ---------------------------------------------------------- modality
async def verify_event_modality(generation_id: str, batch: int = 25) -> dict:
    """Step 9. Every event's modality is read a second time, independently, under the same
    single definition (prompts/modality_rules). Where the two readings differ a referee
    with the full page text decides; its verdict stands only if it sides with one of the
    two readings with confidence >= 0.8. A changed modality supersedes the claim (claims
    are immutable). Only what the referee cannot settle goes to the editor."""
    evs = db.all_rows("SELECT e.id, e.summary, e.modality, e.page_from, e.page_to, e.claim_id,"
                      " (SELECT string_agg(ev.quote, ' | ') FROM claim_evidence ce JOIN evidence ev"
                      "  ON ev.id=ce.evidence_id WHERE ce.claim_id=e.claim_id) AS quotes"
                      " FROM event e WHERE e.generation_id=%s AND e.merged_into IS NULL", generation_id)

    async def run(chunk: list[dict]) -> dict:
        short = {f"e{i}": e for i, e in enumerate(chunk)}
        ctxs = await asyncio.to_thread(
            lambda: [page_text_numbered(generation_id, e["page_from"])[:1500] for e in chunk])
        lines = []
        for (k, e), ctx in zip(short.items(), ctxs):
            lines.append(f"{k} | s{e['page_from']}-{e['page_to']} | {e['summary']} | kanıt: "
                         f"{e['quotes']} | sayfa: {ctx}")
        ref, body = prompts.render("modality_check", events="\n".join(lines))
        out, _ = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                               prompt=ref, schema=schemas.MODALITY_CHECK,
                                               max_tokens=8000, temperature=0.0, thinking=False)
        return {"short": short, "out": out}

    results = await asyncio.gather(*(run(evs[i:i + batch]) for i in range(0, len(evs), batch)))
    disputed = [(r["short"][v["event_id"]], v) for r in results for v in r["out"]["events"]
                if v["event_id"] in r["short"] and v["modality"] != r["short"][v["event_id"]]["modality"]]

    async def referee(e: dict, v: dict) -> tuple[dict, dict, dict | None, int | None]:
        pages = [p for p in range(e["page_from"] - 1, e["page_to"] + 2) if p > 0]
        pages_text = await asyncio.to_thread(
            lambda: "\n".join(page_text_numbered(generation_id, p) for p in pages))
        ref, body = prompts.render(
            "modality_referee", summary=e["summary"], quotes=e["quotes"] or "-", first=e["modality"],
            second=v["modality"], second_reason=v["reason"], pages_text=pages_text)
        try:
            out, call_id = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                                         prompt=ref, schema=schemas.MODALITY_REFEREE,
                                                         pages=pages, max_tokens=6000, temperature=0.0,
                                                         thinking=True)
            return e, v, out, call_id
        except Exception:  # noqa: BLE001 - no verdict: the dispute goes to the editor
            return e, v, None, None

    verdicts = await asyncio.gather(*(referee(e, v) for e, v in disputed))
    stats = {"events": len(evs), "modality_disagreements": len(disputed), "settled_first": 0,
             "settled_second": 0, "sent_to_review": 0}
    with db.tx() as c:
        for e, v, out, call_id in verdicts:
            final = out["modality"] if out and out["confidence"] >= 0.8 and \
                out["modality"] in (e["modality"], v["modality"]) else None
            if final == e["modality"]:
                stats["settled_first"] += 1                 # first reading stands, nothing changes
            elif final is not None:
                stats["settled_second"] += 1
                new_claim = ledger.supersede_claim(
                    c, generation_id, str(e["claim_id"]), payload_update={"modality": final},
                    created_by="knowledge:modality-referee", model_call_id=call_id,
                    note=f"kip {e['modality']} → {final}: {out['reason'][:300]}") if e["claim_id"] else None
                c.execute("UPDATE event SET modality=%s, story_order=NULL, claim_id=coalesce(%s, claim_id)"
                          " WHERE id=%s", (final, new_claim, e["id"]))
            else:
                stats["sent_to_review"] += 1
                c.execute("UPDATE event SET modality='UNCERTAIN', story_order=NULL WHERE id=%s", (e["id"],))
                if e["claim_id"]:
                    third = f"; hakem {out['modality']} ({out['confidence']:.2f}): {out['reason'][:200]}" if out else ""
                    ledger.queue_review(c, generation_id, claim_id=str(e["claim_id"]), priority=1,
                                        reason=f"Olay kipi çözülemedi: çıkarım {e['modality']}, kontrol "
                                               f"{v['modality']} ({v['reason'][:200]}){third}")
    return stats


# ------------------------------------------------------ text budget
# Whole-book list calls (event merge and order, narrative roles, themes, contradictions) go
# through one rule (editor.budget): a list that fits the model's context AND the schema's list
# bound is sent in one call, exactly as before; a longer one is read window by window (page
# order, cut at chapter starts where possible, neighbouring windows overlap) and merged by code.
WINDOW_NOTE = ("\n\nNOT: Bu liste kitabın yalnız s{lo}–s{hi} sayfalarından gelen kayıtları içerir "
               "(kitap uzun olduğu için parça parça okunuyor). Yalnız bu listedeki kimlikleri kullan; "
               "listede olmayan bir şey hakkında karar verme.")


def _chapter_breaks(generation_id: str, spans: list[tuple[int, int]]) -> list[int]:
    """Indices of the page-ordered units that begin a chapter (editor chapters are proposals
    from headings; a book without them has no breaks and is cut by budget alone)."""
    try:
        starts = sorted({c["page_from"] for c in chapters(generation_id)})
    except Exception:  # noqa: BLE001 - chapters are a preference for the cut, not a requirement
        return []
    return [i for i in range(1, len(spans))
            if any(spans[i - 1][0] < s <= spans[i][0] for s in starts)]


async def list_windows(generation_id: str, render: Any, lines: list[str], spans: list[tuple[int, int]],
                       *, max_tokens: int, cap: int | None) -> tuple[list[budget.Window], budget.Fit]:
    """Windows for a whole-book list call. `render(lines) -> body`; `spans[i]` = pages of line i;
    `cap` = the schema bound of the answer's per-item list (a window never holds more items
    than the answer may list, so the bound can no longer cut a book silently)."""
    f = await budget.fit(DIRECTOR, render(lines), max_tokens)
    room = budget.items_room(cap)
    if f.fits and (room is None or len(lines) <= room):
        pf = min((s[0] for s in spans), default=None)
        pt = max((s[1] for s in spans), default=None)
        return [budget.Window(0, 0, len(lines), 0, pf, pt, f.tokens)], f
    overhead = budget.estimate(render([]) + WINDOW_NOTE, f.ratio)
    costs = [budget.estimate(x, f.ratio) + 1 for x in lines]
    breaks = await asyncio.to_thread(_chapter_breaks, generation_id, spans)
    # 5% under the budget: the plan counts with this text's measured characters-per-token,
    # the request is counted by the model's tokenizer.
    wins = budget.plan(costs, int(f.budget.input * 0.95), overhead=overhead, max_units=room,
                       overlap=budget.overlap_items(), breaks=breaks, pages=spans)
    return wins, f


def window_body(body: str, w: budget.Window, windows: list[budget.Window]) -> str:
    return body if len(windows) == 1 else body + WINDOW_NOTE.format(lo=w.page_from, hi=w.page_to)


def _unit(key: str, prefix: str) -> int | None:
    return int(key[len(prefix):]) if key.startswith(prefix) and key[len(prefix):].isdigit() else None


# ------------------------------------------------------ events / timeline
async def merge_events(generation_id: str) -> dict:
    evs = db.all_rows("SELECT e.id, e.page_from, e.page_to, e.modality, e.summary, c.model_call_id"
                      " FROM event e LEFT JOIN claim c ON c.id=e.claim_id WHERE e.generation_id=%s AND"
                      " e.merged_into IS NULL ORDER BY e.page_from, e.page_to", generation_id)
    if not evs:
        return {"events": 0, "merged": 0, "ordered": 0}
    short = {f"e{i}": e for i, e in enumerate(evs)}
    lines = [f"{k} | s{e['page_from']}-{e['page_to']} | {e['modality']} | {e['summary']}"
             for k, e in short.items()]

    def render(ls: list[str]) -> str:
        return prompts.render("merge_events", events="\n".join(ls))[1]

    ref, _ = prompts.render("merge_events", events="")
    wins, fit = await list_windows(generation_id, render, lines,
                                   [(e["page_from"], e["page_to"]) for e in evs], max_tokens=16000,
                                   cap=budget.list_cap(schemas.MERGE_EVENTS, "story_order"))

    async def read(w: budget.Window) -> dict:
        out, _ = await Llm(generation_id).chat(
            DIRECTOR, [{"role": "user", "content": window_body(render(lines[w.start:w.end]), w, wins)}],
            prompt=ref, schema=schemas.MERGE_EVENTS, max_tokens=16000, temperature=0.0, thinking=True)
        return out

    if len(wins) == 1:
        # fits: one call, the whole list, as it always was
        out = await read(wins[0])
        run = budget.Run(wins, [out])
    else:
        run = await budget.map_windows(wins, read)
        if all(r is None for r in run.results):
            raise budget.BudgetError(f"merge_events: no window answered: {run.errors[:3]}")
    hits = [h for r in run.results if r is not None for h in budget.cap_hits(r, schemas.MERGE_EVENTS)]
    # groups: a window may only group its own events; groups sharing an event across the
    # overlap are one group (the same window's two groups never chain into one)
    proposed: list[tuple[int, list[int]]] = []
    for w, r in zip(wins, run.results):
        for g in (r or {}).get("groups", []):
            ids = [u for u in (_unit(x, "e") for x in g["event_ids"]) if u is not None and w.start <= u < w.end]
            if ids:
                proposed.append((w.index, ids))
    sets, refused = budget.union_groups(proposed)
    # a group joined across windows lists the shared event once; a single window's group is
    # used exactly as the model wrote it (its own guards below judge it, as before)
    groups = [[f"e{u}" for u in (proposed[s[0]][1] if len(s) == 1 else
                                 dict.fromkeys(u for gi in s for u in proposed[gi][1]))] for s in sets]
    if len(wins) == 1:
        story = run.results[0]["story_order"]
    else:
        story = [f"e{u}" for u in budget.merge_order(wins, [
            [u for u in (_unit(x, "e") for x in (r or {}).get("story_order", [])) if u is not None]
            for r in run.results])]
    merged = 0
    with db.tx() as c:
        for ids in groups:
            members = [short[x] for x in ids if x in short]
            if len({m["modality"] for m in members}) > 1 or len(members) < 2:
                continue  # never merge a plan with its realisation
            # The extractor listed events of one call separately on purpose: two events
            # from the same call are never one event. Duplicates exist only across calls.
            calls = [m["model_call_id"] for m in members if m["model_call_id"] is not None]
            if len(calls) != len(set(calls)):
                continue
            # Duplicates come from chunk boundaries, so they sit on the same or the next
            # page. Events further apart are consecutive actions, not one event.
            lo = max(m["page_from"] for m in members)
            hi = min(m["page_to"] for m in members)
            if lo - hi > 1:
                continue
            keep = members[0]
            for m in members[1:]:
                c.execute("UPDATE event SET merged_into=%s WHERE id=%s AND merged_into IS NULL",
                          (keep["id"], m["id"]))
                merged += 1
        order = 0
        for x in story:
            e = short.get(x)
            if e and e["modality"] in ("REALIZED", "MEMORY"):
                order += 1
                c.execute("UPDATE event SET story_order=%s WHERE id=%s AND merged_into IS NULL "
                          "AND modality IN ('REALIZED','MEMORY')", (order, e["id"]))
    res = {"events": len(evs), "merged": merged, "ordered": order, "cap_hits": hits}
    if len(wins) > 1:
        # how the list was read: every window's pages, the windows that failed (their events
        # keep no story order), links refused across the overlap. An order across two windows
        # is not invented: windows follow page order, each window orders its own events.
        res["reading"] = budget.report(wins, fit=fit.as_dict(), failed=run.errors,
                                       refused_links=refused)
    return res


def candidate_timeline(generation_id: str) -> list[dict]:
    """Producer-only candidates; never expose this pre-validation view as a user result."""
    return db.all_rows("SELECT id, story_order, page_from, page_to, modality, summary, participants,"
                       " confidence, narrative_role FROM timeline WHERE generation_id=%s ORDER BY story_order NULLS LAST,"
                       " page_from", generation_id)


async def assign_narrative_roles(generation_id: str) -> dict:
    """Importance is relative to the whole book: the director labels each realized
    event's role in the narrative. Returns illustrated pages of key events that have
    no deep scan yet ("Önemli olaylarda" -> book-vision-deep)."""
    tl = candidate_timeline(generation_id)
    if not tl:
        return {"key_events": 0, "pages": []}
    short = {f"e{i}": e for i, e in enumerate(tl)}
    lines = [f"{k} | s{e['page_from']}-{e['page_to']} | {e['summary']}" for k, e in short.items()]

    def render(ls: list[str]) -> str:
        return prompts.render("narrative_roles", events="\n".join(ls))[1]

    ref, _ = prompts.render("narrative_roles", events="")
    # the timeline is in story order; its pages still say where each event is told
    wins, fit = await list_windows(generation_id, render, lines,
                                   [(e["page_from"], e["page_to"]) for e in tl], max_tokens=8000,
                                   cap=budget.list_cap(schemas.NARRATIVE_ROLES, "events"))

    async def read(w: budget.Window) -> dict:
        out, _ = await Llm(generation_id).chat(
            DIRECTOR, [{"role": "user", "content": window_body(render(lines[w.start:w.end]), w, wins)}],
            prompt=ref, schema=schemas.NARRATIVE_ROLES, max_tokens=8000, temperature=0.0, thinking=False)
        return out

    extra: dict = {}
    if len(wins) == 1:
        out = await read(wins[0])
        verdicts = out["events"]
        extra["cap_hits"] = budget.cap_hits(out, schemas.NARRATIVE_ROLES)
    else:
        # Importance is relative to what a window sees: a role is read in every window that
        # holds the event; where two windows disagree the window the event sits most centrally
        # in decides, and the disagreement is reported.
        run = await budget.map_windows(wins, read)
        if all(r is None for r in run.results):
            raise budget.BudgetError(f"narrative_roles: no window answered: {run.errors[:3]}")
        per = []
        for w, r in zip(wins, run.results):
            if r is None:
                per.append(None)
                continue
            got = {}
            for v in r["events"]:
                u = _unit(v["event_id"], "e")
                if u is not None and w.start <= u < w.end and u not in got:
                    got[u] = v["role"]
            per.append(got)
        labels, conflicts = budget.merge_labels(wins, per)
        verdicts = [{"event_id": f"e{u}", "role": role} for u, role in sorted(labels.items())]
        extra["cap_hits"] = [h for r in run.results if r is not None
                             for h in budget.cap_hits(r, schemas.NARRATIVE_ROLES)]
        extra["reading"] = budget.report(wins, fit=fit.as_dict(), failed=run.errors,
                                         role_conflicts=conflicts)
    key = []
    with db.tx() as c:
        for v in verdicts:
            e = short.get(v["event_id"])
            if e:
                c.execute("UPDATE event SET narrative_role=%s WHERE id=%s", (v["role"], e["id"]))
                if v["role"] != "ORDINARY":
                    key.append(e)
        pages = sorted({p for e in key for p in range(e["page_from"], e["page_to"] + 1)})
        rows = c.execute(
            "SELECT p.page_no FROM page p JOIN generation g ON g.book_version_id=p.book_version_id"
            " WHERE g.id=%s AND p.page_no = ANY(%s) AND coalesce(p.nontext_ink, 1) >= %s AND NOT EXISTS"
            " (SELECT 1 FROM page_scan d WHERE d.generation_id=g.id AND d.page_no=p.page_no AND"
            " d.pass='DEEP')", (generation_id, pages, settings().min_illustration_ink)).fetchall()
    return {"key_events": len(key), "pages": [r["page_no"] for r in rows], **extra}


# ------------------------------------------------------- who did what
ACTOR_ROLES = {"A": "ACTOR", "B": "INVOLVED", "C": "ABSENT"}


def _actor_role(probs: dict[str, float], min_p: float) -> str:
    """Presence first, then who acts — with the mass of "absent" left out of that second
    question. Measured on a real book (2026-09-20, 693 pairs): the model tells "in this
    event" from "not in it" almost perfectly, but keeps a fifth to a third of its mass on
    C even where the character plainly acts ("Bilge, yanında kocaman bir kutu ile kapıya
    gelir": A 0,60 / B 0,12 / C 0,28). One threshold over the three raw probabilities
    calls those UNCERTAIN (128 of 693 pairs, 57 of the 146 the extractor itself listed);
    asking the second question only among A and B leaves 44, and the readings it opens up
    are right by eye. A character the reading is not sure is even in the event stays
    UNCERTAIN rather than being sorted by a ratio of two small numbers."""
    if probs["C"] >= min_p:
        return "ABSENT"
    if probs["C"] > 0.5:
        return "UNCERTAIN"
    ab = probs["A"] + probs["B"]
    if ab <= 0:
        return "UNCERTAIN"
    acts = probs["A"] / ab
    return "ACTOR" if acts >= min_p else "INVOLVED" if acts <= 1 - min_p else "UNCERTAIN"


async def attribute_event_actors(generation_id: str, write: bool = True) -> dict:
    """Who did what. `event.participants` is one free-text reading by the extractor: names
    without a probability, not tied to the resolved characters, and in Turkish the subject
    is usually not written at all. Here every (event, character) pair is read on its own
    as a closed-set decision (does the action / takes part / absent) whose probabilities
    come from the model's token distribution (Llm.choose): one deterministic call per
    pair, no option order to be biased by, and several doers are possible.

    Nothing the extractor wrote is changed. Pairs land in `event_actor`; an event goes to
    the editor when a pair stays under the configured probability, when this reading and
    the extractor's list contradict each other, or when the extractor named characters
    and none of them turns out to do the action.

    `write=False` is for measuring on a generation that is already sealed: nothing is
    written to it (the calls are logged without a generation) and every pair's reading
    comes back under `detail`."""
    s = settings()

    # Every database read and write below runs off the event loop: this coroutine shares its
    # loop with up to 48 other activities and with their liveness heartbeats. Run inline, one
    # book's queries and page reads froze the loop for 56-145 s (measured 2026-10-02) and the
    # whole worker's activities were cancelled as "timed out" although none of them had failed.
    def load() -> tuple[list[dict], list[dict], set]:
        chars = db.all_rows("SELECT id, canonical_name, aliases, kind, description FROM character"
                            " WHERE generation_id=%s ORDER BY first_page NULLS LAST, canonical_name",
                            generation_id)
        evs = db.all_rows(
            "SELECT e.id, e.summary, e.page_from, e.page_to, e.participants, e.claim_id,"
            " coalesce(c.payload->>'participants_invalidated'='true',false) AS participants_invalidated,"
            " (SELECT string_agg(ev.quote, ' | ') FROM claim_evidence ce JOIN evidence ev"
            "  ON ev.id=ce.evidence_id WHERE ce.claim_id=e.claim_id) AS quotes"
            " FROM event e LEFT JOIN claim c ON c.id=e.claim_id WHERE e.generation_id=%s AND"
            " e.merged_into IS NULL AND coalesce(c.status,'CANDIDATE') NOT IN ('REJECTED','SUPERSEDED')"
            " ORDER BY e.page_from, e.page_to", generation_id)
        done = {(str(r["event_id"]), str(r["character_id"])) for r in db.all_rows(
            "SELECT event_id, character_id FROM event_actor WHERE generation_id=%s", generation_id)} \
            if write and evs and chars else set()
        return chars, evs, done

    chars, evs, done = await asyncio.to_thread(load)
    stats = {"events": len(evs), "characters": len(chars), "pairs": 0, "pairs_failed": 0,
             "actor": 0, "involved": 0, "absent": 0, "uncertain": 0,
             "extractor_disagreements": 0, "sent_to_review": 0, "invalidated_participant_lists": 0,
             "pairs_skipped": 0, "second_reading": 0, "second_reading_disagreed": 0, "no_doer": 0}
    if not evs or not chars:
        return stats
    detail: list[dict] = []
    names = {str(ch["id"]): {ledger.norm(n) for n in [ch["canonical_name"], *ch["aliases"]]}
             for ch in chars}
    sem = asyncio.Semaphore(s.page_concurrency)
    shared = director_slots()

    def card(ch: dict) -> str:
        also = f" (diğer adları: {', '.join(ch['aliases'])})" if ch["aliases"] else ""
        what = f" — {ch['description']}" if ch["description"] else ""
        return f"{ch['canonical_name']}{also}{what}"[:600]

    async def pair(e: dict, ch: dict, pages: list[int], text: str, seed: int = 17):
        ref, body = prompts.render("event_actor", pages_text=text, summary=e["summary"],
                                   quotes=e["quotes"] or "-", character=card(ch))
        async with sem, shared:
            try:
                probs, call_id = await Llm(generation_id if write else None).choose(
                    DIRECTOR, [{"role": "user", "content": body}], list(ACTOR_ROLES),
                    prompt=ref, pages=pages, seed=seed)
            except Exception:  # noqa: BLE001 - no reading for this pair; it is not written
                return ch, None, None
        return ch, probs, call_id

    def prepare(e: dict) -> tuple[list[int], str, set, list[dict]]:
        pages = [p for p in range(e["page_from"] - 1, e["page_to"] + 1) if p > 0]
        text = "\n".join(page_text_numbered(generation_id, p) for p in pages)
        listed = {ledger.norm(p) for p in e["participants"]}
        # A character who is neither named in the event's own pages nor listed by the
        # extractor is absent by evidence, not by a reading. Asking anyway costs a call per
        # (event x character) — quadratic in book and cast (measured: 8.772 of one book's
        # 9.254 calls) — and can only invent a role the text does not support.
        here = ledger.norm(text + " " + (e["quotes"] or ""))
        todo = [ch for ch in chars if (str(e["id"]), str(ch["id"])) not in done
                and (names[str(ch["id"])] & listed
                     or any(ledger.has_name(here, n) for n in [ch["canonical_name"], *ch["aliases"]]))]
        return pages, text, listed, todo

    def record(e: dict, res: list, listed: set) -> tuple[dict, list[dict], list[dict]]:
        """Writes one event's readings. Returns its own counts (merged on the loop, so worker
        threads never update the shared counters) and the pairs that disagree with the extractor."""
        got = {"pairs": 0, "pairs_failed": 0, "actor": 0, "involved": 0, "absent": 0,
               "uncertain": 0, "invalidated_participant_lists": 0, "extractor_disagreements": 0,
               "no_doer": 0}
        with db.tx() as c:
            for ch, probs, call_id in res:
                got["pairs"] += 1
                if probs is None:
                    got["pairs_failed"] += 1
                    continue
                c.execute(
                    "INSERT INTO event_actor(event_id, character_id, generation_id, p_actor,"
                    " p_involved, p_absent, role, listed_by_extractor, model_call_id) VALUES"
                    " (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (e["id"], ch["id"], generation_id, probs["A"], probs["B"], probs["C"],
                     _actor_role(probs, s.actor_min_probability),
                     bool(names[str(ch["id"])] & listed), call_id))
            # judged on every pair of the event, also those a previous attempt wrote
            rows = c.execute(
                "SELECT ea.*, ch.canonical_name FROM event_actor ea JOIN character ch ON"
                " ch.id=ea.character_id WHERE ea.event_id=%s", (e["id"],)).fetchall()
        for r in rows:
            got[r["role"].lower()] += 1
        unsure = [r for r in rows if r["role"] == "UNCERTAIN"]
        # A correction invalidates the previous extractor list. An unknown
        # list is not a negative assertion that nobody participated. The
        # fresh actor probabilities and genuine uncertainty still apply.
        comparable = not e['participants_invalidated']
        if not comparable:
            got['invalidated_participant_lists'] += 1
        dropped = [r for r in rows if comparable and r["listed_by_extractor"] and r["role"] == "ABSENT"]
        added = [r for r in rows if comparable and not r["listed_by_extractor"] and r["role"] == "ACTOR"]
        no_doer = comparable and any(r["listed_by_extractor"] for r in rows) and \
            not any(r["role"] == "ACTOR" for r in rows)
        got["extractor_disagreements"] += len(dropped) + len(added)
        got["no_doer"] += bool(no_doer and not unsure)
        return got, dropped, added

    def queue(e: dict, why: list[str]) -> None:
        with db.tx() as c:
            ledger.queue_review(c, generation_id, claim_id=str(e["claim_id"]), priority=2,
                                reason="Kim yaptı: " + "; ".join(why))

    async def one(e: dict) -> None:
        pages, text, listed, todo = await asyncio.to_thread(prepare, e)
        stats["pairs_skipped"] += len(chars) - len(todo)
        if not todo:
            return
        res = await asyncio.gather(*(pair(e, ch, pages, text) for ch in todo))
        if not write:
            for ch, probs, _ in res:
                stats["pairs"] += 1
                if probs is None:
                    stats["pairs_failed"] += 1
                    continue
                role = _actor_role(probs, s.actor_min_probability)
                stats[role.lower()] += 1
                detail.append({"pages": [e["page_from"], e["page_to"]], "event": e["summary"],
                               "extractor_participants": e["participants"],
                               "character": ch["canonical_name"], "role": role,
                               "listed_by_extractor": bool(names[str(ch["id"])] & listed),
                               "p_actor": round(probs["A"], 4), "p_involved": round(probs["B"], 4),
                               "p_absent": round(probs["C"], 4)})
            return
        got, dropped, added = await asyncio.to_thread(record, e, res, listed)
        for k, v in got.items():
            stats[k] += v
        # The editor is asked only when the reading CHANGES what a claim says — a listed
        # participant read as absent, an unlisted character read as the doer — and only when
        # a second, independent reading (another seed) agrees. A pair that stays uncertain
        # changes nothing (`event_actors` never reports an uncertain pair as a doer): it is
        # recorded, not queued, so the queue stays readable for a book of any length
        # (measured: 749 of a six-book corpus' 853 queue items were this one kind).
        confirmed = []
        for r in dropped + added:
            ch = next((x for x in chars if str(x["id"]) == str(r["character_id"])), None)
            if ch is None:
                continue
            stats["second_reading"] += 1
            _, probs, _ = await pair(e, ch, pages, text, seed=4241)
            if probs and _actor_role(probs, s.actor_min_probability) == r["role"]:
                confirmed.append(r)
            else:
                stats["second_reading_disagreed"] += 1
        if confirmed and s.actor_review and e["claim_id"]:
            why = []
            drop = [r for r in confirmed if r["listed_by_extractor"]]
            add = [r for r in confirmed if not r["listed_by_extractor"]]
            if drop:
                why.append("çıkarım katılımcı saymış, iki okuma da olayda görmüyor: " + ", ".join(
                    f"{r['canonical_name']} (yok {r['p_absent']:.2f})" for r in drop))
            if add:
                why.append("çıkarımın listesinde yok, iki okuma da eylemi yapan diyor: " + ", ".join(
                    f"{r['canonical_name']} ({r['p_actor']:.2f})" for r in add))
            await asyncio.to_thread(queue, e, why)
            stats["sent_to_review"] += 1

    await asyncio.gather(*(one(e) for e in evs))
    return stats if write else {**stats, "detail": detail}


def build_timeline(generation_id: str) -> list[dict]:
    from . import read_model
    return read_model.timeline(generation_id)


def event_actors(generation_id: str) -> list[dict]:
    from . import read_model
    return read_model.actors(generation_id)


# ----------------------------------------------------- emotions/themes
async def link_emotions_and_themes(generation_id: str) -> dict:
    """Step 10: attach emotions to resolved characters, consolidate themes."""
    with db.tx() as c:
        emotions = c.execute("SELECT id,character_name,page_no,claim_id FROM emotion "
                             "WHERE generation_id=%s", (generation_id,)).fetchall()
        n = 0
        for em in emotions:
            character_id = _emotion_character(c, generation_id, em['character_name'],
                                              em['page_no'], em['claim_id'])
            # Re-evaluate old links too: identity corrections can remove support.
            c.execute("UPDATE emotion SET character_id=%s WHERE id=%s "
                      "AND character_id IS DISTINCT FROM %s", (character_id, em['id'], character_id))
            n += character_id is not None
    th = db.all_rows("SELECT c.id, c.claim, c.source_pages, (SELECT string_agg(e.quote, ' | ') FROM"
                     " claim_evidence ce JOIN evidence e ON e.id=ce.evidence_id WHERE ce.claim_id=c.id)"
                     " AS quotes FROM claim c WHERE c.generation_id=%s AND c.kind='THEME' AND"
                     " c.payload->>'level'='chunk' AND c.status NOT IN "
                     " ('REJECTED','EDITOR_REJECTED','SUPERSEDED') ORDER BY c.id", generation_id)
    if not th:
        return {"emotions_linked": n, "themes": 0}
    short = {f"t{i}": t for i, t in enumerate(th)}
    lines = [f"{k} | s{t['source_pages']} | {t['claim']} | {t['quotes']}" for k, t in short.items()]
    spans = [(min(t["source_pages"] or [0]), max(t["source_pages"] or [0])) for t in th]
    groups, call_id, info = await consolidate_themes(generation_id, lines, spans)
    # The contract is "every input in some group, with its exact id". A group that breaks it
    # is not used; an input no valid group covers is NOT lost and does not stop the book: its
    # chapter-level theme claim simply stays as it is, unconsolidated, and is counted.
    covered = {x for t in groups for x in t["source_ids"]}
    dropped_groups = info["dropped_groups"]
    unconsolidated = sorted(set(short) - covered)
    out = {"themes": groups}
    made = 0
    with db.tx() as c:
        for t in out["themes"]:
            srcs = [short[s] for s in t["source_ids"]]
            evs = []
            for s in srcs:
                source_evidence = c.execute(
                    "SELECT ce.evidence_id,e.page_no,e.quote_verified FROM claim_evidence ce "
                    "JOIN evidence e ON e.id=ce.evidence_id WHERE ce.claim_id=%s AND e.generation_id=%s",
                    (s["id"], generation_id)).fetchall()
                if not source_evidence:
                    raise ValueError("Theme source has no evidence in this generation: " + str(s['id']))
                for r in source_evidence:
                    evs.append((str(r["evidence_id"]), r["quote_verified"], r["page_no"]))
            payload = {"level": "book", "theme": t["theme"]}
            if t.get("windows"):
                payload["windows"] = t["windows"]      # which windows (pages) the theme came from
            if ledger.save_claim(c, generation_id, kind="THEME", subject=t["theme"], claim=t["text"],
                                 evidence=list(dict.fromkeys(evs)), confidence=t["confidence"],
                                 created_by="knowledge:themes", model_call_id=t.get("call_id") or call_id,
                                 payload=payload):
                made += 1
    res = {"emotions_linked": n, "themes": made, "theme_groups_dropped": dropped_groups,
           "themes_left_unconsolidated": len(unconsolidated), "cap_hits": info["cap_hits"]}
    if info.get("reading"):
        res["reading"] = info["reading"]
    return res


THEMES_CONTRACT = ("\nHer girdi kimliğini en az bir tema grubunun source_ids listesinde aynen kullan. "
                   "Yeni kimlik üretme; önek ekleme; hiçbir girdiyi sessizce atlama. "
                   "Birleştirilemeyen temayı kendi kaynak kimliğiyle ayrı koru.")


def _valid_theme_groups(themes: list[dict], allowed: set[str]) -> list[dict]:
    return [t for t in themes if t["source_ids"] and len(t["source_ids"]) == len(set(t["source_ids"]))
            and all(x in allowed for x in t["source_ids"])]


async def consolidate_themes(generation_id: str, lines: list[str], spans: list[tuple[int, int]],
                             prefix: str = "t", level: int = 0) -> tuple[list[dict], int | None, dict]:
    """Chapter-level theme candidates -> book themes (map-reduce). Fits: one call, as before.
    Longer: every window groups its own candidates; groups that share a candidate across an
    overlap are one; then the window groups themselves are consolidated the same way (reduce),
    until one call sees them all. A group keeps the ids of the ORIGINAL candidates, so its
    evidence is still their page quotes, and the windows (pages) it came from."""
    def render(ls: list[str]) -> str:
        return prompts.render("themes", themes="\n".join(ls))[1] + THEMES_CONTRACT

    ref, _ = prompts.render("themes", themes="")
    wins, fit = await list_windows(generation_id, render, lines, spans, max_tokens=6000,
                                   cap=budget.list_cap(schemas.THEMES, "themes", "[]", "source_ids"))
    keys = [f"{prefix}{i}" for i in range(len(lines))]

    async def read(w: budget.Window) -> tuple[dict, int]:
        return await Llm(generation_id).chat(
            DIRECTOR, [{"role": "user", "content": window_body(render(lines[w.start:w.end]), w, wins)}],
            prompt=ref, schema=schemas.THEMES, max_tokens=6000, temperature=0.1, thinking=False)

    if len(wins) == 1:
        out, call_id = await read(wins[0])
        valid = _valid_theme_groups(out["themes"], set(keys))
        return valid, call_id, {"dropped_groups": len(out["themes"]) - len(valid),
                                "cap_hits": budget.cap_hits(out, schemas.THEMES)}
    run = await budget.map_windows(wins, read)
    if all(r is None for r in run.results):
        raise budget.BudgetError(f"themes: no window answered: {run.errors[:3]}")
    proposed: list[tuple[int, list[int]]] = []
    meta: list[dict] = []
    dropped, hits = 0, []
    for w, r in zip(wins, run.results):
        if r is None:
            continue
        out, cid = r
        hits += budget.cap_hits(out, schemas.THEMES)
        own = {keys[i] for i in w.units}
        valid = _valid_theme_groups(out["themes"], own)
        dropped += len(out["themes"]) - len(valid)
        for t in valid:
            proposed.append((w.index, [keys.index(x) for x in t["source_ids"]]))
            meta.append({**t, "call_id": cid, "windows": [w.evidence()]})
    sets, refused = budget.union_groups(proposed)
    groups = []
    for st in sets:
        best = max(st, key=lambda gi: len(proposed[gi][1]))
        src = list(dict.fromkeys(u for gi in st for u in proposed[gi][1]))
        groups.append({"theme": meta[best]["theme"], "text": meta[best]["text"],
                       "confidence": min(meta[gi]["confidence"] for gi in st),
                       "source_ids": [keys[u] for u in src], "call_id": meta[best]["call_id"],
                       "windows": [ev for gi in st for ev in meta[gi]["windows"]]})
    reading = budget.report(wins, level=level, fit=fit.as_dict(), failed=run.errors, refused_links=refused)
    call_id = groups[0]["call_id"] if groups else None
    if len(groups) > 1 and (level == 0 or len(groups) < len(lines)):
        # reduce: the window groups are candidates themselves; same prompt, same contract.
        # Above the first level it recurses only while it still consolidates, so it ends.
        g_lines = [f"g{j} | s{min(spans[keys.index(x)][0] for x in g['source_ids'])}-"
                   f"{max(spans[keys.index(x)][1] for x in g['source_ids'])} | {g['theme']}: {g['text']}"
                   for j, g in enumerate(groups)]
        g_spans = [(min(spans[keys.index(x)][0] for x in g["source_ids"]),
                    max(spans[keys.index(x)][1] for x in g["source_ids"])) for g in groups]
        try:
            top, top_call, top_info = await consolidate_themes(generation_id, g_lines, g_spans, "g", level + 1)
        except Exception as e:  # noqa: BLE001 - the window themes stand, unreduced, and it is said
            reading["reduce_failed"] = f"{type(e).__name__}: {str(e)[:300]}"
        else:
            if 0 < len(top) < len(groups):
                merged = []
                used: set[int] = set()
                for t in top:
                    js = [int(x[1:]) for x in t["source_ids"]]
                    used.update(js)
                    merged.append({"theme": t["theme"], "text": t["text"], "confidence": t["confidence"],
                                   "source_ids": list(dict.fromkeys(x for j in js for x in groups[j]["source_ids"])),
                                   "call_id": t.get("call_id") or top_call,
                                   "windows": [ev for j in js for ev in groups[j]["windows"]]})
                # a window group the reduce left out stays as its window wrote it
                merged += [g for j, g in enumerate(groups) if j not in used]
                groups, call_id = merged, top_call
                dropped += top_info["dropped_groups"]
                hits += top_info["cap_hits"]
                reading["reduce"] = top_info.get("reading") or {"windowed": False}
            else:
                reading["reduce"] = {"skipped": "reduce did not consolidate", "groups": len(groups)}
    return groups, call_id, {"dropped_groups": dropped, "cap_hits": hits, "reading": reading}


# ---------------------------------------------------- contradictions
async def detect_contradictions(generation_id: str) -> dict:
    """Contradictions between FACTS THE TEXT STATES (timeline, character facts). Drawn
    appearance is not judged here: comparing two scans' wording ("beyaz" vs "pembe" skin)
    produced false findings; continuity of drawings is decided only by looking at the
    pictures side by side (vision.compare_character_appearances)."""
    chars = db.all_rows("SELECT canonical_name, aliases, description, identity_status FROM character "
                        "WHERE generation_id=%s", generation_id)
    tl = candidate_timeline(generation_id)
    if not chars and not tl:
        return {"candidates": 0, "skipped": "nothing to compare"}
    head = ("KARAKTERLER (metne göre):\n" + "\n".join(f"- {c['canonical_name']} ({', '.join(c['aliases'])}) "
                                                     f"[{c['identity_status']}]: {c['description']}" for c in chars)
            + "\nGERÇEKLEŞMİŞ OLAYLAR (sırayla):\n")
    lines = [f"{e['story_order']}. s{e['page_from']}-{e['page_to']}: {e['summary']}" for e in tl]

    def render(ls: list[str]) -> str:
        return prompts.render("contradictions", material=head + "\n".join(ls))[1]

    ref, _ = prompts.render("contradictions", material="")
    # A contradiction needs both statements in one reading: a long timeline is read window by
    # window with the character table in every window. Two statements in windows that never
    # meet are not compared here (reported); the final-read text check reads the text itself.
    wins, fit = await list_windows(generation_id, render, lines,
                                   [(e["page_from"], e["page_to"]) for e in tl], max_tokens=12000,
                                   cap=None)

    async def read(w: budget.Window) -> tuple[dict, int]:
        return await Llm(generation_id).chat(
            DIRECTOR, [{"role": "user", "content": window_body(render(lines[w.start:w.end]), w, wins)}],
            prompt=ref, schema=schemas.CONTRADICTIONS, max_tokens=12000, temperature=0.0, thinking=True)

    if len(wins) == 1:
        run = budget.Run(wins, [await read(wins[0])])
    else:
        run = await budget.map_windows(wins, read)
        if all(r is None for r in run.results):
            raise budget.BudgetError(f"contradictions: no window answered: {run.errors[:3]}")
    made, repeated, hits = 0, 0, []
    seen: set[tuple] = set()
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)
        pages = _valid_pages(c, generation_id)
        for w, r in zip(wins, run.results):
            if r is None:
                continue
            out, call_id = r
            hits += budget.cap_hits(out, schemas.CONTRADICTIONS)
            for x in out["candidates"]:
                evs = [e for e in ledger.evidence_from_model(c, generation_id, idx, x["evidence"],
                                                             valid_pages=pages) if e[1]]
                if len({e[0] for e in evs}) < 2:
                    continue        # a contradiction needs the two statements that conflict, verbatim
                key = (x["kind"], tuple(sorted({e[0] for e in evs})))
                if len(wins) > 1 and key in seen:     # the same pair found again in an overlap
                    repeated += 1
                    continue
                seen.add(key)
                payload = {"contradiction_kind": x["kind"]}
                if len(wins) > 1:
                    payload["window"] = w.evidence()
                cid = ledger.save_claim(c, generation_id, kind="EVENT" if x["kind"] == "TIMELINE" else "CHARACTER",
                                        subject=x["kind"], claim=x["description"], evidence=evs,
                                        confidence=x["confidence"], created_by="knowledge:contradictions",
                                        model_call_id=call_id, payload=payload)
                c.execute("INSERT INTO contradiction(generation_id, kind, description, pages, claim_ids,"
                          " confidence) VALUES (%s,%s,%s,%s,%s,%s)",
                          (generation_id, x["kind"], x["description"], x["pages"], [cid] if cid else [],
                           x["confidence"]))
                made += 1
    res = {"candidates": made, "cap_hits": hits}
    if len(wins) > 1:
        res["reading"] = budget.report(wins, fit=fit.as_dict(), failed=run.errors,
                                       repeated_in_overlap=repeated)
    return res
