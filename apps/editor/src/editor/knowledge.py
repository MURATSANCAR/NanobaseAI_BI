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

from . import db, ledger, prompts, schemas
from .config import settings
from .document import page_text_numbered
from .llm import Llm

DIRECTOR = "book-director"
_HEADING = re.compile(r"^[A-ZÇĞİÖŞÜ0-9 ,.'’!?-]{6,60}$")


# --------------------------------------------------------------- chapters
def chapters(generation_id: str) -> list[dict]:
    """Chapters from upper-case headings at the top of a page that is followed by
    body text on the same page (title pages and imprint lines are not chapters).
    Consecutive heading paragraphs are one title ("TABLET PEŞİNDE" + "BİR GÜN")."""
    rows = db.all_rows("SELECT page_no, idx, text FROM paragraph WHERE generation_id=%s"
                       " ORDER BY page_no, idx", generation_id)
    last_page = max((r["page_no"] for r in rows), default=0)
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
        out.insert(0, {"title": "Ön sayfalar", "page_from": 1, "page_to": starts[0][0] - 1})
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
        text = "\n".join(page_text_numbered(gid, p) for p in range(a, b + 1))
        ref, body = prompts.render("extract_knowledge", page_from=str(a), page_to=str(b),
                                   pages_text=text, visual_summary=_visual_summary(gid, a, b),
                                   corrections=corrections_text(gid))
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
            if int(e.get("paragraph") or 0) > 0 and not idx.verify(int(e["page"]), e["quote"], "TEXT"):
                bad.append(f"s{e['page']}: “{e['quote']}”")
    return {**st, "unverified": bad if total and len(bad) / total > 0.2 else []}


def _route(st: ChunkState) -> str:
    return "extract" if st.get("unverified") and st.get("attempts", 0) < 2 else "persist"


def _persist(st: ChunkState) -> ChunkState:
    gid, o, call_id = st["generation_id"], st["out"], st["call_id"]
    counts = {"mentions": 0, "events": 0, "emotions": 0, "themes": 0, "dropped_no_evidence": 0,
              "dropped_non_story": 0}
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, gid)
        pages = _valid_pages(c, gid)
        non_story = {p for p in o.get("non_story_pages", []) if st["page_from"] <= p <= st["page_to"]}
        for p in non_story:
            c.execute("INSERT INTO page_role(generation_id, page_no, role, source, model_call_id)"
                      " VALUES (%s,%s,'NON_STORY','extract',%s) ON CONFLICT DO NOTHING", (gid, p, call_id))

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
        for m in o["character_mentions"]:
            evs = ledger.evidence_from_model(c, gid, idx, m["evidence"], valid_pages=pages)
            if not evs:
                counts["dropped_no_evidence"] += 1
                continue
            c.execute("INSERT INTO character_mention(generation_id, page_no, surface_name, via,"
                      " appearance, resolution, confidence, evidence_id) VALUES"
                      " (%s,%s,%s,%s,%s,'UNRESOLVED',%s,%s)",
                      (gid, m["page"] if m["page"] in pages else evs[0][2], m["surface_name"],
                       m["via"], db.J({"description": m["description"]}), m["confidence"], evs[0][0]))
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
    """Story pages in chunks of `size`; front matter (imprint, author bios) is
    not story text and would yield false characters."""
    front = {p for c in chapters(generation_id) if c["title"] == "Ön sayfalar"
             for p in range(c["page_from"], c["page_to"] + 1)}
    with db.tx() as c:
        for p in front:
            c.execute("INSERT INTO page_role(generation_id, page_no, role, source) VALUES"
                      " (%s,%s,'FRONT_MATTER','layout') ON CONFLICT DO NOTHING", (generation_id, p))
    pages = [r["page_no"] for r in db.all_rows(
        "SELECT DISTINCT page_no FROM paragraph WHERE generation_id=%s ORDER BY page_no", generation_id)
        if r["page_no"] not in front]
    return [(pages[i], pages[min(i + size, len(pages)) - 1]) for i in range(0, len(pages), size)]


# ------------------------------------------------- agent-facing writes
def _agent_evidence(c, generation_id: str, evidence: list[dict]) -> list[tuple[str, bool, int]]:
    """Evidence supplied by Hermes must be verbatim page text; otherwise refused."""
    idx = ledger.PageIndex.load(c, generation_id)
    pages = _valid_pages(c, generation_id)
    for e in evidence or []:
        kind = "VISUAL" if int(e.get("paragraph") or 0) == 0 else "TEXT"
        if int(e.get("page") or 0) not in pages or not idx.verify(int(e["page"]), e.get("quote", ""), kind):
            raise ValueError(f"kanıt doğrulanamadı: sayfa {e.get('page')}: “{e.get('quote')}”")
    evs = ledger.evidence_from_model(c, generation_id, idx, evidence, valid_pages=pages)
    if not evs:
        raise ValueError("kanıt zorunlu (Kaynaksız iddia üretilemez)")
    return evs


def save_character_candidate(generation_id: str, name: str, page: int, description: str,
                             evidence: list[dict], confidence: float, via: str = "TEXT") -> dict:
    with db.tx() as c:
        evs = _agent_evidence(c, generation_id, evidence)
        c.execute("INSERT INTO character_mention(generation_id, page_no, surface_name, via, appearance,"
                  " resolution, confidence, evidence_id) VALUES (%s,%s,%s,%s,%s,'UNRESOLVED',%s,%s)",
                  (generation_id, page, name, via, db.J({"description": description}),
                   confidence, evs[0][0]))
    return {"saved": True, "status": "UNRESOLVED", "evidence": len(evs)}


def save_event(generation_id: str, summary: str, modality: str, page_from: int, page_to: int,
               participants: list[str], evidence: list[dict], confidence: float,
               importance: float = 0.5) -> dict:
    with db.tx() as c:
        evs = _agent_evidence(c, generation_id, evidence)
        cid = ledger.save_claim(c, generation_id, kind="EVENT", subject=", ".join(participants),
                                claim=summary, evidence=evs, confidence=confidence,
                                created_by="hermes", payload={"modality": modality})
        row = c.execute("INSERT INTO event(generation_id, page_from, page_to, summary, modality,"
                        " participants, importance, confidence, claim_id) VALUES"
                        " (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (generation_id, min(page_from, page_to), max(page_from, page_to), summary,
                         modality, participants, importance, confidence, cid)).fetchone()
    return {"event_id": str(row["id"]), "claim_id": cid, "modality": modality}


def save_emotion(generation_id: str, character: str, page: int, emotion: str, intensity: float,
                 trigger: str, evidence: list[dict], confidence: float) -> dict:
    with db.tx() as c:
        evs = _agent_evidence(c, generation_id, evidence)
        cid = ledger.save_claim(c, generation_id, kind="EMOTION", subject=character,
                                claim=f"{character} {emotion} hissediyor ({trigger})", evidence=evs,
                                confidence=confidence, created_by="hermes",
                                payload={"emotion": emotion, "intensity": intensity, "trigger": trigger})
        ch = c.execute("SELECT id FROM character WHERE generation_id=%s AND (canonical_name ILIKE %s"
                       " OR %s = ANY(aliases)) LIMIT 1", (generation_id, character, character)).fetchone()
        c.execute("INSERT INTO emotion(generation_id, character_id, character_name, page_no, emotion,"
                  " intensity, trigger, confidence, claim_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                  (generation_id, ch["id"] if ch else None, character, page, emotion, intensity,
                   trigger, confidence, cid))
    return {"claim_id": cid}


# ------------------------------------------------------ identity merge
async def resolve_character_identity(generation_id: str) -> dict:
    """Names are resolved from the TEXT only. The model groups text mentions; the
    alias list is not the model's to write: it is exactly the set of names under
    which the merged mentions occur in the book, so a figure label or a note can
    never become an alias. Appearance is not part of identity here; drawn figures are
    attached afterwards by reference images (vision.resolve_visual_identity).
    CONFIRMED needs >= 0.85 and evidence on at least two pages."""
    ms = db.all_rows(
        "SELECT cm.id, cm.page_no, cm.surface_name, cm.confidence, e.quote FROM character_mention cm"
        " JOIN evidence e ON e.id=cm.evidence_id WHERE cm.generation_id=%s AND cm.character_id IS NULL"
        " AND cm.via IN ('TEXT','BOTH') AND cm.surface_name IS NOT NULL ORDER BY cm.page_no",
        generation_id)
    if not ms:
        return {"characters": 0}
    short = {str(m["id"]): f"m{i}" for i, m in enumerate(ms)}
    back = {v: k for k, v in short.items()}
    lines = [f"{short[str(m['id'])]} | s{m['page_no']} | {m['surface_name']} | “{m['quote'][:200]}”" for m in ms]
    ref, body = prompts.render("resolve_identity", mentions="\n".join(lines),
                               corrections=corrections_text(generation_id))
    out, call_id = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                                 prompt=ref, schema=schemas.IDENTITY,
                                                 max_tokens=16000, temperature=0.0, thinking=True)
    by_id = {str(m["id"]): m for m in ms}
    conflicted = {back[x["mention_id"]] for x in out["conflicts"] if x["mention_id"] in back}
    # A name belongs to ONE character. If the grouping puts mentions of the same name into
    # different characters, the name goes where most of its mentions are and the stray
    # mentions follow it (seen: one "Robobi" mention grouped with the professor made
    # "Robobi" his alias).
    votes: dict[str, dict[int, int]] = {}
    for gi, ch in enumerate(out["characters"]):
        for x in ch["mention_ids"]:
            if x in back:
                n = ledger.norm(by_id[back[x]]["surface_name"])
                votes.setdefault(n, {}).setdefault(gi, 0)
                votes[n][gi] += 1
    owner = {n: max(v, key=lambda gi: (v[gi], -gi)) for n, v in votes.items()}
    groups: dict[int, list[str]] = {gi: [] for gi in range(len(out["characters"]))}
    for gi, ch in enumerate(out["characters"]):
        for x in ch["mention_ids"]:
            if x in back:
                groups[owner[ledger.norm(by_id[back[x]]["surface_name"])]].append(back[x])
    claimed: set[str] = set()
    made = []
    with db.tx() as c:
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
            aliases = [n for n in names if ledger.norm(n) != ledger.norm(canonical)]
            pages = sorted({by_id[m]["page_no"] for m in mids})
            conf = float(ch["identity_confidence"])
            if len(pages) < 2:
                conf = min(conf, 0.7)
            status = "CONFIRMED" if conf >= 0.85 and not (set(mids) & conflicted) else "CANDIDATE"
            evs = []
            for m in mids[:8]:
                e = c.execute("SELECT evidence_id FROM character_mention WHERE id=%s", (m,)).fetchone()
                evs.append((str(e["evidence_id"]), True, by_id[m]["page_no"]))
            cid = ledger.save_claim(
                c, generation_id, kind="CHARACTER_IDENTITY", subject=canonical,
                claim=canonical + (f" (diğer adlar: {', '.join(aliases)})" if aliases else "")
                + f": {ch['description']}",
                evidence=evs, confidence=conf, created_by="knowledge:identity", model_call_id=call_id,
                payload={"merge_basis": ch["merge_basis"], "aliases": aliases, "identity_status": status})
            row = c.execute(
                "INSERT INTO character(generation_id, canonical_name, aliases, description,"
                " identity_status, identity_confidence, first_page, claim_id, kind) VALUES"
                " (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (generation_id, canonical, aliases, ch["description"], status, conf, pages[0], cid,
                 ch.get("kind") or "UNKNOWN")).fetchone()
            for m in mids:
                sure = float(by_id[m]["confidence"]) >= 0.75 and conf >= 0.75 and m not in conflicted
                c.execute("UPDATE character_mention SET character_id=%s, resolution=%s WHERE id=%s",
                          (row["id"], "RESOLVED" if sure else "UNCERTAIN", m))
            made.append({"name": canonical, "aliases": aliases, "status": status, "confidence": conf,
                         "pages": pages[:12]})
            if status != "CONFIRMED" and len(pages) >= 3 and cid:
                ledger.queue_review(c, generation_id, claim_id=cid, priority=2,
                                    reason=f"Karakter kimliği kesinleşmedi ({conf:.2f}): "
                                           f"{canonical} — {ch['merge_basis']}")
        for m in conflicted:
            c.execute("UPDATE character_mention SET resolution='UNCERTAIN' WHERE id=%s", (m,))
    return {"characters": len(made), "confirmed": sum(1 for m in made if m["status"] == "CONFIRMED"),
            "unresolved_mentions": len(ms) - len(claimed), "conflicts": len(out["conflicts"]),
            "list": made}


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
        lines = []
        for k, e in short.items():
            ctx = page_text_numbered(generation_id, e["page_from"])[:1500]
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
        ref, body = prompts.render(
            "modality_referee", summary=e["summary"], quotes=e["quotes"] or "-", first=e["modality"],
            second=v["modality"], second_reason=v["reason"],
            pages_text="\n".join(page_text_numbered(generation_id, p) for p in pages))
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
    ref, body = prompts.render("merge_events", events="\n".join(lines))
    out, _ = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}], prompt=ref,
                                           schema=schemas.MERGE_EVENTS, max_tokens=16000,
                                           temperature=0.0, thinking=True)
    merged = 0
    with db.tx() as c:
        for g in out["groups"]:
            members = [short[x] for x in g["event_ids"] if x in short]
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
        for x in out["story_order"]:
            e = short.get(x)
            if e and e["modality"] in ("REALIZED", "MEMORY"):
                order += 1
                c.execute("UPDATE event SET story_order=%s WHERE id=%s AND merged_into IS NULL "
                          "AND modality IN ('REALIZED','MEMORY')", (order, e["id"]))
    return {"events": len(evs), "merged": merged, "ordered": order}


def build_timeline(generation_id: str) -> list[dict]:
    """Realized (and remembered) events only, in story order."""
    return db.all_rows("SELECT id, story_order, page_from, page_to, modality, summary, participants,"
                       " confidence, narrative_role FROM timeline WHERE generation_id=%s ORDER BY story_order NULLS LAST,"
                       " page_from", generation_id)


async def assign_narrative_roles(generation_id: str) -> dict:
    """Importance is relative to the whole book: the director labels each realized
    event's role in the narrative. Returns illustrated pages of key events that have
    no deep scan yet ("Önemli olaylarda" -> book-vision-deep)."""
    tl = build_timeline(generation_id)
    if not tl:
        return {"key_events": 0, "pages": []}
    short = {f"e{i}": e for i, e in enumerate(tl)}
    ref, body = prompts.render("narrative_roles", events="\n".join(
        f"{k} | s{e['page_from']}-{e['page_to']} | {e['summary']}" for k, e in short.items()))
    out, _ = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}], prompt=ref,
                                           schema=schemas.NARRATIVE_ROLES, max_tokens=8000,
                                           temperature=0.0, thinking=False)
    key = []
    with db.tx() as c:
        for v in out["events"]:
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
    return {"key_events": len(key), "pages": [r["page_no"] for r in rows]}


# ----------------------------------------------------- emotions/themes
async def link_emotions_and_themes(generation_id: str) -> dict:
    """Step 10: attach emotions to resolved characters, consolidate themes."""
    with db.tx() as c:
        n = c.execute(
            "UPDATE emotion em SET character_id=ch.id FROM character ch WHERE em.generation_id=%s"
            " AND ch.generation_id=em.generation_id AND em.character_id IS NULL AND"
            " (lower(ch.canonical_name)=lower(em.character_name) OR"
            "  lower(em.character_name) = ANY(SELECT lower(a) FROM unnest(ch.aliases) a))",
            (generation_id,)).rowcount
    th = db.all_rows("SELECT c.id, c.claim, c.source_pages, (SELECT string_agg(e.quote, ' | ') FROM"
                     " claim_evidence ce JOIN evidence e ON e.id=ce.evidence_id WHERE ce.claim_id=c.id)"
                     " AS quotes FROM claim c WHERE c.generation_id=%s AND c.kind='THEME' AND"
                     " c.payload->>'level'='chunk'", generation_id)
    if not th:
        return {"emotions_linked": n, "themes": 0}
    short = {f"t{i}": t for i, t in enumerate(th)}
    ref, body = prompts.render("themes", themes="\n".join(
        f"{k} | s{t['source_pages']} | {t['claim']} | {t['quotes']}" for k, t in short.items()))
    out, call_id = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                                 prompt=ref, schema=schemas.THEMES, max_tokens=6000,
                                                 temperature=0.1, thinking=False)
    made = 0
    with db.tx() as c:
        for t in out["themes"]:
            srcs = [short[s] for s in t["source_ids"] if s in short]
            evs = []
            for s in srcs:
                for r in c.execute("SELECT ce.evidence_id, e.page_no, e.quote_verified FROM claim_evidence"
                                   " ce JOIN evidence e ON e.id=ce.evidence_id WHERE ce.claim_id=%s",
                                   (s["id"],)):
                    evs.append((str(r["evidence_id"]), r["quote_verified"], r["page_no"]))
            if ledger.save_claim(c, generation_id, kind="THEME", subject=t["theme"], claim=t["text"],
                                 evidence=evs[:10], confidence=t["confidence"],
                                 created_by="knowledge:themes", model_call_id=call_id,
                                 payload={"level": "book", "theme": t["theme"]}):
                made += 1
    return {"emotions_linked": n, "themes": made}


# ---------------------------------------------------- contradictions
async def detect_contradictions(generation_id: str) -> dict:
    """Contradictions between FACTS THE TEXT STATES (timeline, character facts). Drawn
    appearance is not judged here: comparing two scans' wording ("beyaz" vs "pembe" skin)
    produced false findings; continuity of drawings is decided only by looking at the
    pictures side by side (vision.compare_character_appearances)."""
    chars = db.all_rows("SELECT canonical_name, aliases, description, identity_status FROM character "
                        "WHERE generation_id=%s", generation_id)
    tl = build_timeline(generation_id)
    if not chars and not tl:
        return {"candidates": 0, "skipped": "nothing to compare"}
    material = (
        "KARAKTERLER (metne göre):\n" + "\n".join(f"- {c['canonical_name']} ({', '.join(c['aliases'])}) "
                                                   f"[{c['identity_status']}]: {c['description']}" for c in chars)
        + "\nGERÇEKLEŞMİŞ OLAYLAR (sırayla):\n" + "\n".join(
            f"{e['story_order']}. s{e['page_from']}-{e['page_to']}: {e['summary']}" for e in tl))
    ref, body = prompts.render("contradictions", material=material)
    out, call_id = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                                 prompt=ref, schema=schemas.CONTRADICTIONS,
                                                 max_tokens=12000, temperature=0.0, thinking=True)
    made = 0
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)
        pages = _valid_pages(c, generation_id)
        for x in out["candidates"]:
            evs = [e for e in ledger.evidence_from_model(c, generation_id, idx, x["evidence"],
                                                         valid_pages=pages) if e[1]]
            if len({e[0] for e in evs}) < 2:
                continue        # a contradiction needs the two statements that conflict, verbatim
            cid = ledger.save_claim(c, generation_id, kind="EVENT" if x["kind"] == "TIMELINE" else "CHARACTER",
                                    subject=x["kind"], claim=x["description"], evidence=evs,
                                    confidence=x["confidence"], created_by="knowledge:contradictions",
                                    model_call_id=call_id, payload={"contradiction_kind": x["kind"]})
            c.execute("INSERT INTO contradiction(generation_id, kind, description, pages, claim_ids,"
                      " confidence) VALUES (%s,%s,%s,%s,%s,%s)",
                      (generation_id, x["kind"], x["description"], x["pages"], [cid] if cid else [],
                       x["confidence"]))
            made += 1
    return {"candidates": made}
