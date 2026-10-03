"""Character relation graph: the actor -> event -> object triangle over the
evidence ledger (portal graph view, `network`).

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


# ------------------------------------------------------------ book network
def network(generation_id: str, include_all_modalities: bool = False) -> dict:
    """Whole-book character network for a picture, from the usable events of the
    ledger: node = character with the number of fact events it takes part in
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
