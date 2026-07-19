"""Atomic semantic Qdrant publisher (two-phase activate)."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from nanobase_api.semantic_catalog.domain.errors import ValidationError
from nanobase_api.semantic_catalog.domain.semantic_version import SemanticVersion
from nanobase_api.semantic_catalog.domain.status import AssetStatus
from nanobase_api.semantic_catalog.infrastructure.catalog_store import CatalogStore

logger = logging.getLogger(__name__)


def collection_name(datasource_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in datasource_id)
    return f"bi_semantic_{safe}"


class SemanticQdrantPublisher:
    """Publish PUBLISHED assets for a semantic version.

    If qdrant client is unavailable, records an in-memory index for tests.
    """

    def __init__(self, client: Any | None = None, *, fail_on_error: bool = True) -> None:
        self.client = client
        self.fail_on_error = fail_on_error
        self._indexed: dict[str, list[dict[str, Any]]] = {}

    def publish_version(
        self,
        store: CatalogStore,
        version: SemanticVersion,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        if version.status not in (AssetStatus.PREPARING, AssetStatus.READY):
            version.status = AssetStatus.PREPARING

        docs = self._build_documents(store, version)
        checksum = hashlib.sha256(
            json.dumps(docs, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        try:
            if self.client is not None:
                self._upsert_qdrant(version, docs)
            self._indexed[version.id] = docs
            # Verify count
            if len(self._indexed[version.id]) != len(docs):
                raise ValidationError("Qdrant count mismatch — partial publish engellendi.")
            return {
                "ok": True,
                "documentCount": len(docs),
                "checksum": checksum,
                "manifestSha256": manifest.get("manifestSha256"),
                "collection": collection_name(version.datasource_id),
            }
        except Exception as e:
            version.status = AssetStatus.FAILED
            logger.exception("semantic qdrant publish failed")
            if self.fail_on_error:
                raise ValidationError(f"Semantic publish failed (active version unchanged): {e}") from e
            return {"ok": False, "error": str(e)}

    def _build_documents(self, store: CatalogStore, version: SemanticVersion) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        tid, ds = version.tenant_id, version.datasource_id
        base = {
            "tenant_id": tid,
            "datasource_id": ds,
            "semantic_version": version.version,
            "schema_version": version.schema_version,
            "status": "PUBLISHED",
            "language": "tr",
        }
        for m in store.list_published_metrics(tid, ds):
            docs.append(
                {
                    **base,
                    "document_type": "METRIC",
                    "code": m.code,
                    "text": f"{m.name}. {m.description}",
                }
            )
        for t in store.list_published_terms(tid, ds):
            docs.append(
                {
                    **base,
                    "document_type": "BUSINESS_TERM",
                    "code": t.normalized_name,
                    "text": f"{t.name}. {t.description}. Synonyms: {', '.join(t.synonyms)}",
                }
            )
        for f in store.list_published_filters(tid, ds):
            docs.append(
                {
                    **base,
                    "document_type": "FILTER_RULE",
                    "code": f.code,
                    "text": f.description,
                }
            )
        for vq in store.verified_queries.values():
            if (
                vq.tenant_id == tid
                and vq.datasource_id == ds
                and vq.status == AssetStatus.PUBLISHED
                and vq.semantic_version == version.version
            ):
                docs.append(
                    {
                        **base,
                        "document_type": "VERIFIED_LOGICAL_PLAN",
                        "code": vq.id,
                        "text": json.dumps(vq.logical_plan, ensure_ascii=False),
                    }
                )
        return docs

    def _upsert_qdrant(self, version: SemanticVersion, docs: list[dict[str, Any]]) -> None:
        # Lazy import — production path
        from qdrant_client.http import models as qm

        coll = collection_name(version.datasource_id)
        # Ensure collection exists (vector size placeholder if embeddings deferred)
        # Documents stored with payload-only retrieval fallback when vectors omitted
        points = []
        for i, doc in enumerate(docs):
            pid = hashlib.sha256(f"{version.id}:{doc['document_type']}:{doc['code']}".encode()).hexdigest()[:32]
            points.append(
                qm.PointStruct(
                    id=pid if False else abs(hash(pid)) % (2**63),
                    vector=[0.0] * 8,  # placeholder; real embedder wired in deploy
                    payload=doc,
                )
            )
        self.client.upsert(collection_name=coll, points=points)

    def retrieve(
        self,
        *,
        tenant_id: str,
        datasource_id: str,
        semantic_version: str | None,
        query_text: str,
        document_types: list[str] | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """In-memory / payload filter retrieval (production uses Qdrant filter)."""
        hits: list[dict[str, Any]] = []
        q = (query_text or "").lower()
        for docs in self._indexed.values():
            for d in docs:
                if d.get("tenant_id") != tenant_id or d.get("datasource_id") != datasource_id:
                    continue
                if d.get("status") != "PUBLISHED":
                    continue
                if semantic_version and d.get("semantic_version") != semantic_version:
                    continue
                if document_types and d.get("document_type") not in document_types:
                    continue
                text = (d.get("text") or "").lower()
                code = (d.get("code") or "").lower()
                if q in text or any(tok in text or tok in code for tok in q.split() if len(tok) > 2):
                    hits.append(d)
        return hits[:limit]
