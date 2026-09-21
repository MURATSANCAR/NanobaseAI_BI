"""book_retrieval tools: embedding index in the editor's own Qdrant, evidence
search with book-embedding + book-reranker."""

from __future__ import annotations

import uuid

from qdrant_client import AsyncQdrantClient, models

from . import db, source
from .config import settings
from .llm import Llm

PASSAGES = "editor_passages_v1"
DIM = 4096
NS = uuid.UUID("6f1c7a52-1b7e-4a55-9b1f-7e1d2c3b4a50")
QUERY_INSTRUCTION = "Given a question about a book, retrieve the passages from the book that answer it"
RERANK_INSTRUCTION = "Does this passage from the book contain evidence that answers the question?"

_q: AsyncQdrantClient | None = None


def qdrant() -> AsyncQdrantClient:
    global _q
    if _q is None:
        s = settings()
        _q = AsyncQdrantClient(url=s.qdrant_url, api_key=s.qdrant_key or None, timeout=120)
    return _q


async def _ensure(name: str) -> None:
    q = qdrant()
    if not await q.collection_exists(name):
        await q.create_collection(name, vectors_config=models.VectorParams(
            size=DIM, distance=models.Distance.COSINE))
        for field in ("generation_id", "kind", "universe"):
            await q.create_payload_index(name, field, models.PayloadSchemaType.KEYWORD)


def _passages(generation_id: str) -> list[dict]:
    out = source.passages(generation_id)
    out += [{"kind": "event", "page_no": r["page_from"], "ref": f"event:{r['id']}",
             "text": f"[{r['modality']}] {r['summary']}"}
            for r in db.all_rows("SELECT id, page_from, modality, summary FROM event WHERE "
                                 "generation_id=%s AND merged_into IS NULL", generation_id)]
    out += [{"kind": "scene", "page_no": r["page_no"], "ref": f"scene:{r['id']}",
             "text": r["description"]}
            for r in db.all_rows("SELECT id, page_no, description FROM visual_region WHERE "
                                 "generation_id=%s AND kind='scene'", generation_id)]
    out += [{"kind": "character", "page_no": r["first_page"] or 1, "ref": f"character:{r['id']}",
             "text": f"{r['canonical_name']} ({', '.join(r['aliases'])}): {r['description']}"}
            for r in db.all_rows("SELECT id, first_page, canonical_name, aliases, description FROM "
                                 "character WHERE generation_id=%s", generation_id)]
    return [p for p in out if p["text"] and p["text"].strip()]


async def embed_passages(generation_id: str, batch: int = 64) -> dict:
    await _ensure(PASSAGES)
    ps = _passages(generation_id)
    llm = Llm(generation_id)
    q = qdrant()
    for i in range(0, len(ps), batch):
        chunk = ps[i:i + batch]
        vecs = await llm.embed([p["text"] for p in chunk])
        await q.upsert(PASSAGES, points=[models.PointStruct(
            id=str(uuid.uuid5(NS, f"{generation_id}:{p['ref']}")), vector=v,
            payload={**p, "generation_id": generation_id}) for p, v in zip(chunk, vecs)])
    return {"indexed": len(ps), "collection": PASSAGES}


async def rerank_evidence(query: str, candidates: list[str], generation_id: str | None = None) -> list[dict]:
    scores = await Llm(generation_id).rerank(query, candidates, instruction=RERANK_INSTRUCTION)
    return sorted(({"index": i, "score": s, "text": t} for i, (t, s) in
                   enumerate(zip(candidates, scores))), key=lambda x: -x["score"])


async def search_book_evidence(generation_id: str, query: str, k: int = 8,
                               kinds: list[str] | None = None) -> list[dict]:
    """Embedding recall (top 40) -> reranker -> top k, each with page reference."""
    from .outputs import current
    selected = current(generation_id, "search_index")
    if not selected["available"]:
        raise ValueError("Current revision search index is unavailable; rebuild required")
    build_key = selected["artifact"]["build_key"]
    await _ensure(PASSAGES)
    vec = (await Llm(generation_id).embed([query], instruction=QUERY_INSTRUCTION))[0]
    must = [models.FieldCondition(key="generation_id", match=models.MatchValue(value=generation_id))]
    must.append(models.FieldCondition(key="build_key", match=models.MatchValue(value=build_key)))
    if kinds:
        must.append(models.FieldCondition(key="kind", match=models.MatchAny(any=kinds)))
    hits = (await qdrant().query_points(PASSAGES, query=vec, limit=40, with_payload=True,
                                        query_filter=models.Filter(must=must))).points
    if not hits:
        return []
    ranked = await rerank_evidence(query, [h.payload["text"] for h in hits], generation_id)
    out = []
    for r in ranked[:k]:
        p = hits[r["index"]].payload
        out.append({"page": p["page_no"], "paragraph": p.get("paragraph_idx"), "kind": p["kind"],
                    "ref": p["ref"], "text": p["text"], "rerank_score": round(r["score"], 4),
                    "embedding_score": round(hits[r["index"]].score, 4)})
    latest = current(generation_id, "search_index")
    if not latest["available"] or latest["artifact"]["build_key"] != build_key:
        raise ValueError("Search inputs changed while the query was running; retry")
    return out


def search_character_history(generation_id: str, name: str) -> dict:
    ch = db.all_rows("SELECT id, canonical_name, aliases, description, identity_status,"
                     " identity_confidence, first_page FROM character WHERE generation_id=%s AND"
                     " (canonical_name ILIKE %s OR %s ILIKE ANY(aliases))", generation_id, name, name)
    ids = [c["id"] for c in ch]
    return {
        "characters": ch,
        "mentions": db.all_rows(
            "SELECT cm.page_no, cm.surface_name, cm.via, cm.resolution, cm.confidence, e.quote FROM"
            " character_mention cm JOIN evidence e ON e.id=cm.evidence_id WHERE cm.generation_id=%s"
            " AND (cm.character_id = ANY(%s) OR cm.surface_name ILIKE %s) ORDER BY cm.page_no",
            generation_id, ids, name),
        "emotions": db.all_rows(
            "SELECT page_no, emotion, intensity, trigger, confidence FROM emotion WHERE generation_id=%s"
            " AND (character_id = ANY(%s) OR character_name ILIKE %s) ORDER BY page_no",
            generation_id, ids, name),
        "events": db.all_rows(
            "SELECT page_from, page_to, modality, summary FROM event WHERE generation_id=%s AND"
            " merged_into IS NULL AND EXISTS (SELECT 1 FROM unnest(participants) p WHERE p ILIKE %s)"
            " ORDER BY page_from", generation_id, f"%{name}%"),
    }


async def search_universe_canon(universe: str, query: str, k: int = 8) -> list[dict]:
    """Only editor-approved, non-superseded canon entries are searchable."""
    rows = db.all_rows("SELECT id, kind, key, value, approved_by, approved_at FROM canon_entry "
                       "WHERE universe=%s AND superseded_by IS NULL", universe)
    if not rows or not query.strip():
        return rows[:k]
    texts = [f"{r['kind']} {r['key']}: {r['value']}" for r in rows]
    ranked = await rerank_evidence(query, texts)
    return [{**rows[r["index"]], "rerank_score": round(r["score"], 4)} for r in ranked[:k]]


async def embed_snapshot(snapshot: dict, build_key: str) -> dict:
    """Write an immutable index namespace; readers use the DB's current pointer."""
    from .outputs import snapshot_passages
    await _ensure(PASSAGES)
    passages=snapshot_passages(snapshot)
    llm=Llm(snapshot['generation_id'])
    for start in range(0,len(passages),64):
        chunk=passages[start:start+64]
        vecs=await llm.embed([p['text'] for p in chunk])
        if len(vecs)!=len(chunk) or any(len(v)!=DIM for v in vecs):
            raise ValueError('Embedding output count/dimension mismatch')
        await qdrant().upsert(PASSAGES,wait=True,points=[models.PointStruct(
            id=str(uuid.uuid5(NS,f"{snapshot['generation_id']}:{build_key}:{p['ref']}")),vector=v,
            payload={**p,'generation_id':snapshot['generation_id'],'build_key':build_key,
                     'knowledge_revision':snapshot['revision']}) for p,v in zip(chunk,vecs)])
    count=(await qdrant().count(PASSAGES,exact=True,count_filter=models.Filter(must=[
        models.FieldCondition(key='generation_id',match=models.MatchValue(value=snapshot['generation_id'])),
        models.FieldCondition(key='build_key',match=models.MatchValue(value=build_key))]))).count
    if count!=len(passages): raise ValueError('Index staging count mismatch')
    return {'collection':PASSAGES,'build_key':build_key,'revision':snapshot['revision'],'indexed':count}
