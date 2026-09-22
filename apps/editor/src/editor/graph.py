"""book_graph tools: the actor -> event -> object triangle over the evidence
ledger, plus co-actor synergies and graph-proximity recommendations.

This is brainapi2's "triangle of attribution" (actor / event / target) with the
editor's own rule bolted on: every edge is an already-usable event (accepted
claim, verified quote, same-generation evidence) and carries its page+quote
provenance. Reads only -- no writes, no schema, nothing book-specific.

An event's ACTOR characters are the subjects; its INVOLVED characters are the
objects. An event with no involved character is still an actor -> event edge
(intransitive). By default only REALIZED and MEMORY events are graphed: a plan,
a dream or a lie is not a fact and must not be asserted as one (event.modality).
"""

from __future__ import annotations

from . import db

FACT_MODALITIES = ("REALIZED", "MEMORY")


def _modalities(include_all: bool) -> tuple[str, ...]:
    return ("REALIZED", "MEMORY", "PLAN", "DREAM", "IMAGINATION", "JOKE", "LIE",
            "HYPOTHETICAL", "UNCERTAIN") if include_all else FACT_MODALITIES


def _resolve(generation_id: str, name: str) -> dict | None:
    """A character by canonical name or alias (case-insensitive). None if unknown."""
    return db.one(
        "SELECT id, canonical_name, aliases FROM character "
        "WHERE generation_id=%s AND (lower(canonical_name)=lower(%s) "
        "OR EXISTS (SELECT 1 FROM unnest(aliases) a WHERE lower(a)=lower(%s)))",
        generation_id, name, name)


def _evidence_by_event(generation_id: str, modalities: tuple[str, ...]) -> dict[str, list[dict]]:
    """event_id -> up to a few (page, quote) rows, from the event's usable claim."""
    rows = db.all_rows(
        "SELECT e.id AS event_id, ev.page_no, ev.quote, ev.quote_verified "
        "FROM usable_event e "
        "JOIN claim_evidence ce ON ce.claim_id=e.claim_id "
        "JOIN evidence ev ON ev.id=ce.evidence_id "
        "WHERE e.generation_id=%s AND e.modality = ANY(%s) "
        "ORDER BY ev.page_no",
        generation_id, list(modalities))
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(str(r["event_id"]), []).append(
            {"page": r["page_no"], "quote": r["quote"], "verified": r["quote_verified"]})
    return out


def _event_roles(generation_id: str, modalities: tuple[str, ...]) -> dict[str, dict]:
    """event_id -> {summary, modality, importance, page_from, actors[], involved[]}.

    Each actor/involved carries its character id, name and the probability the
    closed-set reader gave that role (event_actor.p_actor / p_involved)."""
    rows = db.all_rows(
        "SELECT e.id AS event_id, e.summary, e.modality, e.importance, e.page_from, "
        "       ea.character_id, ea.role, ea.p_actor, ea.p_involved, c.canonical_name "
        "FROM usable_event e "
        "JOIN event_actor ea ON ea.event_id=e.id AND ea.generation_id=e.generation_id "
        "JOIN character c ON c.id=ea.character_id "
        "WHERE e.generation_id=%s AND e.modality = ANY(%s) AND ea.role IN ('ACTOR','INVOLVED') "
        "ORDER BY e.page_from",
        generation_id, list(modalities))
    events: dict[str, dict] = {}
    for r in rows:
        eid = str(r["event_id"])
        ev = events.setdefault(eid, {
            "summary": r["summary"], "modality": r["modality"],
            "importance": r["importance"], "page_from": r["page_from"],
            "actors": [], "involved": []})
        who = {"character_id": str(r["character_id"]), "name": r["canonical_name"],
               "p": r["p_actor"] if r["role"] == "ACTOR" else r["p_involved"]}
        (ev["actors"] if r["role"] == "ACTOR" else ev["involved"]).append(who)
    return events


# --------------------------------------------------------------- triples
def triples(generation_id: str, character: str | None = None,
            include_all_modalities: bool = False) -> dict:
    """actor -> event -> object edges, each with modality, importance and page+quote
    evidence. `character` (name or alias) keeps only edges that name that character
    as actor or object. Facts only unless include_all_modalities is set."""
    mods = _modalities(include_all_modalities)
    focus_id = None
    if character:
        c = _resolve(generation_id, character)
        if not c:
            return {"character": character, "resolved": False, "triples": []}
        focus_id = str(c["id"])
    events = _event_roles(generation_id, mods)
    ev_evidence = _evidence_by_event(generation_id, mods)
    out: list[dict] = []
    for eid, ev in events.items():
        evidence = ev_evidence.get(eid, [])
        objects = ev["involved"] or [None]        # intransitive event -> one edge, no object
        for actor in ev["actors"]:
            for obj in objects:
                if obj is not None and obj["character_id"] == actor["character_id"]:
                    continue
                if focus_id and focus_id not in (
                        actor["character_id"], obj["character_id"] if obj else None):
                    continue
                out.append({
                    "actor": actor["name"], "p_actor": round(actor["p"], 3),
                    "event": ev["summary"], "modality": ev["modality"],
                    "importance": round(ev["importance"], 3),
                    "object": obj["name"] if obj else None,
                    "p_object": round(obj["p"], 3) if obj else None,
                    "evidence": evidence})
    out.sort(key=lambda t: -t["importance"])
    return {"character": character, "resolved": True if character else None,
            "modalities": list(mods), "count": len(out), "triples": out}


# ---------------------------------------------------- co-actors / synergies
def _affinity(generation_id: str, character: str, mods: tuple[str, ...]) -> tuple[dict | None, dict]:
    """For the focus character, every other character sharing an event with it, with
    a weighted affinity and the shared events. Affinity of a shared event =
    importance * p(focus in event) * p(other in event); summed over shared events."""
    c = _resolve(generation_id, character)
    if not c:
        return None, {}
    focus_id = str(c["id"])
    events = _event_roles(generation_id, mods)
    peers: dict[str, dict] = {}
    for eid, ev in events.items():
        members = {m["character_id"]: m for m in ev["actors"] + ev["involved"]}
        if focus_id not in members:
            continue
        p_focus = members[focus_id]["p"]
        for cid, m in members.items():
            if cid == focus_id:
                continue
            score = ev["importance"] * p_focus * m["p"]
            peer = peers.setdefault(cid, {"character_id": cid, "name": m["name"],
                                          "affinity": 0.0, "shared": []})
            peer["affinity"] += score
            peer["shared"].append({"event": ev["summary"], "page": ev["page_from"],
                                   "importance": round(ev["importance"], 3)})
    return c, peers


def synergies(generation_id: str, character: str,
              include_all_modalities: bool = False) -> dict:
    """Every character that co-occurs with the focus character in an event (unranked
    set), each with the shared events. brainapi2's entity/synergies, evidence-bound."""
    mods = _modalities(include_all_modalities)
    c, peers = _affinity(generation_id, character, mods)
    if c is None:
        return {"character": character, "resolved": False, "synergies": []}
    items = sorted(peers.values(), key=lambda p: -p["affinity"])
    for p in items:
        p["affinity"] = round(p["affinity"], 4)
        p["shared_count"] = len(p["shared"])
    return {"character": c["canonical_name"], "resolved": True,
            "count": len(items), "synergies": items}


def recommend(generation_id: str, character: str, k: int = 5,
              include_all_modalities: bool = False) -> dict:
    """Top-k characters most related to the focus character by graph proximity
    (weighted shared events), each with a one-line reason and its top shared event."""
    mods = _modalities(include_all_modalities)
    c, peers = _affinity(generation_id, character, mods)
    if c is None:
        return {"character": character, "resolved": False, "recommendations": []}
    ranked = sorted(peers.values(), key=lambda p: -p["affinity"])[:k]
    out = []
    for p in ranked:
        top = max(p["shared"], key=lambda s: s["importance"])
        out.append({"name": p["name"], "affinity": round(p["affinity"], 4),
                    "shared_count": len(p["shared"]),
                    "reason": f"{len(p['shared'])} ortak olayda birlikte; en önemlisi "
                              f"s.{top['page']}: {top['event']}"})
    return {"character": c["canonical_name"], "resolved": True, "recommendations": out}


# ------------------------------------------------------------ book network
def network(generation_id: str, include_all_modalities: bool = False) -> dict:
    """Whole-book character network for a picture, from the same usable events as
    triples: node = character with the number of fact events it takes part in
    (actor or involved), edge = the number of fact events two characters share.
    Aliases ride along so a caller can find a named character in free text."""
    mods = _modalities(include_all_modalities)
    counts: dict[str, int] = {}
    pairs: dict[tuple[str, str], int] = {}
    for ev in _event_roles(generation_id, mods).values():
        members = sorted({m["character_id"] for m in ev["actors"] + ev["involved"]})
        for cid in members:
            counts[cid] = counts.get(cid, 0) + 1
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                pairs[(a, b)] = pairs.get((a, b), 0) + 1
    chars = {str(r["id"]): r for r in db.all_rows(
        "SELECT id, canonical_name, aliases FROM character WHERE generation_id=%s AND id = ANY(%s)",
        generation_id, list(counts))} if counts else {}
    nodes = sorted(({"id": cid, "name": chars[cid]["canonical_name"],
                     "aliases": list(chars[cid]["aliases"] or []), "count": n}
                    for cid, n in counts.items() if cid in chars),
                   key=lambda n: (-n["count"], n["name"]))
    edges = sorted(({"a": a, "b": b, "weight": w} for (a, b), w in pairs.items()
                    if a in chars and b in chars), key=lambda e: -e["weight"])
    return {"generation_id": generation_id, "modalities": list(mods),
            "nodes": nodes, "edges": edges}
