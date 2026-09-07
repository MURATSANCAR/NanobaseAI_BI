"""The catalog → BGE-M3 → Qdrant, so a question can find its tables among three hundred.

The prompt cannot carry the schema: nine thousand columns is six times a 24k-token context. Which
tables go in has to be decided before the model is called, and for anything the certified catalog
does not already cover, decided by what the question means.

What is indexed is the catalog, not the database — the profiles the pipeline built, with the meanings
the vendor dictionary supplied. Two kinds of point per table:

  * the table itself: its name, what it is, and the columns it holds
  * every column that anybody described, on its own

A column hit routes to its table, which is what makes "iskonto oranı" reach the invoice table through
`TOTALDISCOUNTS` rather than through the word "fatura" never appearing in the question.

    QDRANT_URL=http://qdrant:6333 BI_EMBED_URL=http://embed:8083/v1/embeddings \\
    SEMANTIC_STORE_DSN=... python backend/scripts/index_catalog_qdrant.py

Re-run after every pipeline run: the index is derived from the catalog and stale entries route
questions at tables that have since been renamed or dropped.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semantic_layer.config import SemanticSettings          # noqa: E402
from semantic_layer.store.catalog_store import open_store    # noqa: E402

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
EMBED_URL = os.environ.get("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings")
VECTOR_SIZE = int(os.environ.get("BI_EMBED_DIM", "1024"))
BATCH = int(os.environ.get("BI_EMBED_BATCH", "32"))


@dataclass
class Point:
    id: int
    entity: str
    table: str
    column: Optional[str]
    text: str


def _http_json(method: str, url: str, body: Optional[dict] = None,
               headers: Optional[dict] = None, timeout: int = 120) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json",
                                          **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def embed(texts: list[str], api_key: str) -> list[list[float]]:
    from semantic_layer.runtime.table_router import embed_request

    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        out.extend(embed_request(EMBED_URL, texts[i:i + BATCH], api_key))
        print(f"  gömüldü {min(i + BATCH, len(texts))}/{len(texts)}", end="\r", flush=True)
    print()
    return out


def points_for(profiles) -> list[Point]:
    """One point for the table, one for every column anybody described.

    A table's own point carries its column names, so a question naming a column reaches the table even
    when that column carries no description of its own.
    """
    points: list[Point] = []
    for p in profiles:
        names = [c.name for c in p.columns]
        head = f"{p.entity} ({p.table_name})"
        if p.description:
            head += f" — {p.description}"
        # Column names are worth carrying, but a four-hundred-column list drowns the description that
        # actually says what the table is for.
        points.append(Point(len(points) + 1, p.entity, p.table_name, None,
                            f"{head}\nkolonlar: {', '.join(names[:80])}"))
        for c in p.columns:
            meaning = (c.description or "").strip()
            if not meaning:
                continue
            values = ""
            if c.is_enum() and c.meaningful_values():
                values = " · değerler: " + ", ".join(v for v, _ in c.meaningful_values()[:10])
            points.append(Point(len(points) + 1, p.entity, p.table_name, c.name,
                                f"{p.entity}.{c.name} — {meaning}{values}"))
    return points


def main() -> int:
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn)
    profiles = store.list_profiles(s.datasource_id)
    if not profiles:
        print(f"katalog boş ({s.store_dsn}, datasource={s.datasource_id}) — önce pipeline'ı çalıştırın",
              file=sys.stderr)
        return 1

    points = points_for(profiles)
    collection = os.environ.get("SEMANTIC_ROUTER_COLLECTION", f"semantic_catalog_{s.datasource_id}")
    print(f"katalog: {len(profiles)} tablo → {len(points)} nokta ({collection})")

    api_key = os.environ.get("BI_EMBED_API_KEY") or os.environ.get("CONTRACT_API_KEY", "")
    vectors = embed([p.text for p in points], api_key)
    if vectors and len(vectors[0]) != VECTOR_SIZE:
        print(f"vektör boyutu {len(vectors[0])} != {VECTOR_SIZE}", file=sys.stderr)
        return 1

    # Rebuilt, not merged: a table that left the catalog has to leave the index with it, or a question
    # gets routed at a table the schema no longer has.
    try:
        _http_json("DELETE", f"{QDRANT_URL}/collections/{collection}")
    except Exception:  # noqa: BLE001
        pass
    _http_json("PUT", f"{QDRANT_URL}/collections/{collection}",
               {"vectors": {"size": VECTOR_SIZE, "distance": "Cosine"}})

    for i in range(0, len(points), 256):
        batch = [{"id": p.id, "vector": v,
                  "payload": {"entity": p.entity, "table": p.table, "column": p.column, "text": p.text}}
                 for p, v in zip(points[i:i + 256], vectors[i:i + 256])]
        _http_json("PUT", f"{QDRANT_URL}/collections/{collection}/points?wait=true", {"points": batch})

    info = _http_json("GET", f"{QDRANT_URL}/collections/{collection}")
    print(f"{collection}: {info.get('result', {}).get('points_count')} nokta yazıldı")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
