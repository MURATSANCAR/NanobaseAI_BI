"""Qdrant schema retrieval for NL2SQL plan enrichment."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
EMBED_URL = os.environ.get("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings")
EMBED_KEY = (
    os.environ.get("BI_EMBED_API_KEY")
    or os.environ.get("CONTRACT_API_KEY")
    or os.environ.get("OPENAI_API_KEY")
    or "nanobase-local"
)


def collection_for(datasource_id: str) -> str:
    return os.environ.get("BI_SCHEMA_COLLECTION") or f"bi_schema_{datasource_id}"


async def _embed(text: str) -> list[float]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            EMBED_URL,
            headers={"Authorization": f"Bearer {EMBED_KEY}", "Content-Type": "application/json"},
            json={"texts": [text]},
        )
        r.raise_for_status()
        data = r.json()
    vectors = data.get("embeddings") or data.get("data")
    if isinstance(vectors, list) and vectors and isinstance(vectors[0], dict):
        vectors = [v["embedding"] for v in sorted(vectors, key=lambda x: x.get("index", 0))]
    if not vectors:
        raise RuntimeError("empty embedding")
    return list(vectors[0])


async def retrieve_schema_context(
    question: str,
    datasource_id: str,
    *,
    top_k: int = 12,
) -> dict[str, Any]:
    """Return retrieved schema snippets for the question (empty if collection missing)."""
    coll = collection_for(datasource_id)
    try:
        vec = await _embed(question)
        async with httpx.AsyncClient(timeout=30.0) as client:
            # existence
            cr = await client.get(f"{QDRANT_URL}/collections/{coll}")
            if cr.status_code >= 400:
                return {"ok": False, "collection": coll, "hits": [], "hint_extra": ""}
            sr = await client.post(
                f"{QDRANT_URL}/collections/{coll}/points/search",
                json={
                    "vector": vec,
                    "limit": top_k,
                    "with_payload": True,
                },
            )
            sr.raise_for_status()
            result = sr.json().get("result") or []
    except Exception as e:
        return {"ok": False, "collection": coll, "hits": [], "hint_extra": "", "error": str(e)[:200]}

    hits = []
    lines = [f"Retrieved schema context for datasource '{datasource_id}' (Qdrant {coll}):"]
    seen_tables: set[str] = set()
    for hit in result:
        payload = hit.get("payload") or {}
        score = hit.get("score")
        text = str(payload.get("text") or "")[:500]
        table = payload.get("table")
        schema = payload.get("schema")
        kind = payload.get("kind")
        fq = f"{schema}.{table}" if schema and table else (table or "")
        if fq:
            seen_tables.add(str(fq))
        hits.append(
            {
                "score": score,
                "kind": kind,
                "table": fq,
                "column": payload.get("column"),
                "text": text,
            }
        )
        lines.append(f"- [{kind}] {fq} score={score:.3f}: {text[:220]}")

    return {
        "ok": True,
        "collection": coll,
        "hits": hits,
        "tables": sorted(seen_tables),
        "hint_extra": "\n".join(lines) if hits else "",
    }
