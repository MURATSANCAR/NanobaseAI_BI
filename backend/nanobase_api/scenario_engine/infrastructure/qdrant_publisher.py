"""Publish scenario paraphrases to Qdrant with real or deterministic embeddings."""

from __future__ import annotations

import hashlib
import os
from typing import Any

from nanobase_api.scenario_engine.domain.scenario import ScenarioInstance, ScenarioParaphrase
from nanobase_api.scenario_engine.domain.status import ScenarioStatus


def _deterministic_vector(text: str, dim: int = 64) -> list[float]:
    """Fallback embedding when BI_EMBED_URL unavailable — stable for exact-ish match tests."""
    out: list[float] = []
    for i in range(dim):
        h = hashlib.sha256(f"{i}:{text}".encode("utf-8")).digest()
        out.append((h[0] / 255.0) * 2 - 1)
    # L2 normalize
    norm = sum(x * x for x in out) ** 0.5 or 1.0
    return [x / norm for x in out]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts. Production requires BI_EMBED_URL unless deterministic embed allowed."""
    allow_det = os.environ.get("SCENARIO_ALLOW_DETERMINISTIC_EMBED", "1").lower() in (
        "1",
        "true",
        "yes",
    )
    url = os.environ.get("BI_EMBED_URL", "").rstrip("/")
    if url:
        try:
            import urllib.request

            payload = json_dumps({"input": texts}).encode("utf-8")
            req = urllib.request.Request(
                f"{url}/v1/embeddings" if not url.endswith("embeddings") else url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json_loads(resp.read().decode("utf-8"))
            vectors = []
            for item in data.get("data") or []:
                vectors.append(list(item.get("embedding") or []))
            if len(vectors) == len(texts) and texts:
                return vectors
        except Exception as e:
            if not allow_det:
                raise RuntimeError(f"BI_EMBED_URL failed: {e}") from e
    elif not allow_det:
        raise RuntimeError("BI_EMBED_URL required for scenario publish (set SCENARIO_ALLOW_DETERMINISTIC_EMBED=1 for dev)")
    return [_deterministic_vector(t) for t in texts]


def json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


def json_loads(s: str) -> Any:
    import json

    return json.loads(s)


class ScenarioQdrantPublisher:
    def __init__(self, url: str | None = None) -> None:
        self.url = (url or os.environ.get("QDRANT_URL") or "http://127.0.0.1:6333").rstrip("/")

    def collection_name(self, datasource_id: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in datasource_id)
        return f"bi_scenario_{safe}"

    def ensure_collection(self, datasource_id: str, dim: int = 64) -> None:
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qm

            client = QdrantClient(url=self.url)
            name = self.collection_name(datasource_id)
            existing = {c.name for c in client.get_collections().collections}
            if name not in existing:
                client.create_collection(
                    collection_name=name,
                    vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
                )
            # Payload indexes for filtered retrieval
            for field in (
                "tenant_id",
                "datasource_id",
                "schema_version",
                "semantic_version",
                "language",
                "status",
                "scenario_family",
            ):
                try:
                    client.create_payload_index(
                        collection_name=name,
                        field_name=field,
                        field_schema=qm.PayloadSchemaType.KEYWORD,
                    )
                except Exception:
                    pass
        except Exception:
            # Qdrant optional in unit tests
            return

    def publish(
        self,
        *,
        instances: list[ScenarioInstance],
        paraphrases: list[ScenarioParaphrase],
    ) -> dict[str, Any]:
        if not instances:
            return {"upserted": 0}
        ds = instances[0].datasource_id
        texts = [p.text for p in paraphrases]
        vectors = embed_texts(texts) if texts else []
        dim = len(vectors[0]) if vectors else 64
        self.ensure_collection(ds, dim=dim)

        by_id = {i.id: i for i in instances}
        points = []
        for p, vec in zip(paraphrases, vectors):
            inst = by_id.get(p.scenario_id)
            if inst is None or inst.status != ScenarioStatus.PUBLISHED:
                continue
            payload = {
                "tenant_id": p.tenant_id,
                "datasource_id": p.datasource_id,
                "schema_version": inst.schema_version,
                "semantic_version": inst.semantic_version,
                "language": p.language,
                "status": ScenarioStatus.PUBLISHED.value,
                "scenario_family": inst.family,
                "scenario_id": inst.id,
                "scenario_code": inst.scenario_code,
                "text": p.text,
                "normalized_question_hash": p.normalized_hash,
            }
            points.append({"id": p.id, "vector": vec, "payload": payload})
            p.embedding_id = p.id

        upserted = self._upsert(ds, points)
        return {"upserted": upserted, "collection": self.collection_name(ds)}

    def _upsert(self, datasource_id: str, points: list[dict[str, Any]]) -> int:
        if not points:
            return 0
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qm

            client = QdrantClient(url=self.url)
            client.upsert(
                collection_name=self.collection_name(datasource_id),
                points=[
                    qm.PointStruct(id=self._point_id(p["id"]), vector=p["vector"], payload=p["payload"])
                    for p in points
                ],
            )
            return len(points)
        except Exception:
            return 0

    @staticmethod
    def _point_id(pid: str) -> str:
        # Qdrant accepts UUID or unsigned int; hash string to uuid5-like hex
        h = hashlib.md5(pid.encode("utf-8")).hexdigest()
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"

    def search(
        self,
        *,
        question: str,
        tenant_id: str,
        datasource_id: str,
        schema_version: str,
        semantic_version: str,
        language: str = "tr",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        vec = embed_texts([question])[0]
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http import models as qm

            client = QdrantClient(url=self.url)
            flt = qm.Filter(
                must=[
                    qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id)),
                    qm.FieldCondition(key="datasource_id", match=qm.MatchValue(value=datasource_id)),
                    qm.FieldCondition(key="schema_version", match=qm.MatchValue(value=schema_version)),
                    qm.FieldCondition(key="semantic_version", match=qm.MatchValue(value=semantic_version)),
                    qm.FieldCondition(key="language", match=qm.MatchValue(value=language)),
                    qm.FieldCondition(key="status", match=qm.MatchValue(value="PUBLISHED")),
                ]
            )
            hits = client.search(
                collection_name=self.collection_name(datasource_id),
                query_vector=vec,
                query_filter=flt,
                limit=limit,
            )
            return [
                {
                    "score": float(h.score),
                    "scenario_id": (h.payload or {}).get("scenario_id"),
                    "scenario_code": (h.payload or {}).get("scenario_code"),
                    "text": (h.payload or {}).get("text"),
                }
                for h in hits
            ]
        except Exception:
            return []
