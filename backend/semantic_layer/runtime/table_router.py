"""Which tables a question is about, when the catalog does not already say.

The certified catalog answers this exactly and instantly for everything it covers: a term someone has
already written down maps to a column, and the column names its table. That path is not replaced here
and must always run first — it is deterministic, it is auditable, and it costs nothing.

This is for the rest. A documented ERP schema is three hundred tables and nine thousand columns; a
question that names none of the certified vocabulary has, without something like this, no way to
reach the four tables that answer it. The schema cannot go into the prompt — measured against a
24k-token context it is six times too large — so the choice is not *whether* to select tables, but
whether the selection is informed.

What makes it possible now is that the tables can be described in the language the questions arrive
in. Embedding "Item Transactions" and hoping it matches "malzeme hareketleri" does not work; the
vendor's Turkish structure document is what changed that.

Nothing here is required. No Qdrant, no embedding service, an unreachable one, a collection that was
never built — each yields no routing at all, and the caller keeps the behaviour it had. A router that
guesses when it cannot search would be worse than no router: it would send generated SQL at tables
chosen by accident.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

#: Below this cosine similarity a hit says more about the corpus than about the question. A router
#: that returns its best match no matter how poor turns "no idea" into a confident wrong table.
MIN_SCORE = float(os.environ.get("SEMANTIC_ROUTER_MIN_SCORE", "0.35"))


def _http_json(method: str, url: str, body: Optional[dict] = None,
               headers: Optional[dict] = None, timeout: float = 10.0) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def embed_request(url: str, texts: list[str], api_key: str = "", timeout: float = 120.0) -> list[list[float]]:
    """Embed a batch, whichever embedding service this deployment runs.

    Two are in use and they do not agree. The GPU host serves llama.cpp's OpenAI-compatible endpoint,
    which requires `input` and answers anything else with `"input" or "content" must be provided`. The
    application host runs a wrapper of its own that takes `texts`. Both were probed, neither is going
    away, and a caller that picks one silently produces an empty index on the other — which is what an
    existing collection with zero points in it turned out to be.

    So: the standard field first, the wrapper's field when the service rejects it.
    """
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
    last: Exception
    for field in ("input", "texts"):
        try:
            res = _http_json("POST", url, {field: texts}, headers=headers, timeout=timeout)
        except (urllib.error.HTTPError, RuntimeError) as e:
            last = e
            continue
        vectors = res.get("embeddings") or res.get("data") or []
        if vectors and isinstance(vectors[0], dict):
            vectors = [v["embedding"] for v in sorted(vectors, key=lambda x: x.get("index", 0))]
        if len(vectors) == len(texts):
            return [list(v) for v in vectors]
        last = RuntimeError(f"embedding service returned {len(vectors)} vectors for {len(texts)} texts")
    raise RuntimeError(f"embedding service {url} accepted neither 'input' nor 'texts': {last}")


class TableRouter:
    """Question → the entities most likely to answer it, by vector search over the catalog.

    `embed` and `search` are injected in tests; in a deployment they are the embedding service and
    Qdrant that the stack already runs.
    """

    def __init__(self, datasource_id: str, *,
                 qdrant_url: str = "", embed_url: str = "", collection: str = "",
                 api_key: str = "", timeout: float = 0.0,
                 embed: Optional[Callable[[str], list[float]]] = None,
                 search: Optional[Callable[[list[float], int], list[dict]]] = None):
        self.datasource_id = datasource_id
        self.qdrant_url = (qdrant_url or os.environ.get("QDRANT_URL", "")).rstrip("/")
        self.embed_url = embed_url or os.environ.get("BI_EMBED_URL", "")
        self.collection = collection or os.environ.get(
            "SEMANTIC_ROUTER_COLLECTION", f"semantic_catalog_{datasource_id}")
        self.api_key = api_key or os.environ.get("BI_EMBED_API_KEY") or os.environ.get("CONTRACT_API_KEY", "")
        # A router is an optimisation on the way to an answer, never something a user waits on: if it
        # has not returned by now the question is better served by the catalog alone.
        self.timeout = timeout or float(os.environ.get("SEMANTIC_ROUTER_TIMEOUT_SEC", "3"))
        self._embed = embed
        self._search = search
        self._failed = False

    @property
    def configured(self) -> bool:
        return bool((self._embed and self._search) or (self.qdrant_url and self.embed_url))

    def embed(self, text: str) -> list[float]:
        if self._embed:
            return self._embed(text)
        return embed_request(self.embed_url, [text], self.api_key, self.timeout)[0]

    def search(self, vector: list[float], limit: int) -> list[dict]:
        if self._search:
            return self._search(vector, limit)
        res = _http_json("POST", f"{self.qdrant_url}/collections/{self.collection}/points/search",
                         {"vector": vector, "limit": limit, "with_payload": True}, timeout=self.timeout)
        return list(res.get("result") or [])

    def route(self, question: str, known: set[str], *, limit: int = 6) -> list[tuple[str, float]]:
        """The entities this question is about, best first — only ones the catalog actually holds.

        A payload naming a table that is not in this scan is dropped rather than returned: a
        relationship or a FROM clause pointing at a table nobody catalogued is worse than a miss.
        """
        if not question.strip() or not known or not self.configured or self._failed:
            return []
        try:
            # Ask for more points than tables wanted: several columns of one table can occupy the
            # top of the list, and they collapse to a single entity.
            hits = self.search(self.embed(question), max(limit * 4, 20))
        except (OSError, urllib.error.URLError, RuntimeError, ValueError, TimeoutError) as e:
            # Once. A router that retries a dead service on every question makes every question slow.
            self._failed = True
            log.info("table router unavailable, falling back to the catalog alone: %s", e)
            return []

        best: dict[str, float] = {}
        for hit in hits:
            payload = hit.get("payload") or {}
            entity = str(payload.get("entity") or "").upper()
            score = float(hit.get("score") or 0.0)
            if entity in known and score >= MIN_SCORE:
                best[entity] = max(best.get(entity, 0.0), score)
        ranked = sorted(best.items(), key=lambda kv: -kv[1])[:limit]
        if ranked:
            log.info("table router: %s", ", ".join(f"{e} {s:.2f}" for e, s in ranked))
        return ranked
