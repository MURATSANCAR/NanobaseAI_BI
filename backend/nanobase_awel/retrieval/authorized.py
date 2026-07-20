"""Authorized schema retrieval with tenant/datasource filters."""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

from nanobase_awel.contracts.errors import SCHEMA_RETRIEVAL_UNAVAILABLE, WorkflowError
from nanobase_awel.operators.context_sanitizer import sanitize_planning_context

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
EMBED_URL = os.environ.get("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings")
EMBED_KEY = (
    os.environ.get("BI_EMBED_API_KEY")
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


def build_qdrant_filter(
    *,
    tenant_id: str,
    datasource_id: str,
    schema_version: int | str | None = None,
    allowed_schemas: list[str] | None = None,
    database_type: str | None = None,
    allowed_owners: list[str] | None = None,
    semantic_version: str | None = None,
    status: str | None = None,
) -> dict[str, Any] | None:
    """Payload filter — must include datasource; tenant/status only when set.

    Neon/Postgres schema index payloads typically have no ``status`` field.
    Default is therefore no status clause (Oracle callers may pass status=\"ACTIVE\").
    """
    must: list[dict[str, Any]] = [
        {"key": "datasource_id", "match": {"value": datasource_id}},
    ]
    if tenant_id and tenant_id != "default":
        must.append({"key": "tenant_id", "match": {"value": tenant_id}})
    if schema_version is not None:
        must.append({"key": "schema_version", "match": {"value": schema_version}})
    if allowed_schemas:
        # Postgres uses schema; Oracle payloads also set schema=owner
        must.append({"key": "schema", "match": {"any": list(allowed_schemas)}})
    if database_type:
        must.append({"key": "database_type", "match": {"value": database_type.upper()}})
        # Oracle scanner stamps status=ACTIVE; include only for typed Oracle searches.
        if status is None and database_type.upper() in ("ORACLE", "ADB"):
            status = "ACTIVE"
    if allowed_owners:
        must.append(
            {"key": "owner", "match": {"any": [o.upper() for o in allowed_owners]}}
        )
    if semantic_version:
        must.append({"key": "semantic_version", "match": {"value": semantic_version}})
    if status:
        must.append({"key": "status", "match": {"value": status}})
    return {"must": must}


async def retrieve_authorized_schema(
    question: str,
    *,
    tenant_id: str,
    datasource_id: str,
    max_documents: int = 30,
    schema_version: int | str | None = None,
    allowed_schemas: list[str] | None = None,
    database_type: str | None = None,
    allowed_owners: list[str] | None = None,
    semantic_version: str | None = None,
    fail_closed: bool = False,
) -> dict[str, Any]:
    coll = collection_for(datasource_id)
    qfilter = build_qdrant_filter(
        tenant_id=tenant_id,
        datasource_id=datasource_id,
        schema_version=schema_version,
        allowed_schemas=allowed_schemas,
        database_type=database_type,
        allowed_owners=allowed_owners,
        semantic_version=semantic_version,
    )
    try:
        vec = await _embed(question)
        body: dict[str, Any] = {
            "vector": vec,
            "limit": max_documents,
            "with_payload": True,
        }
        if qfilter:
            body["filter"] = qfilter
        async with httpx.AsyncClient(timeout=30.0) as client:
            cr = await client.get(f"{QDRANT_URL}/collections/{coll}")
            if cr.status_code >= 400:
                if fail_closed:
                    raise WorkflowError(
                        SCHEMA_RETRIEVAL_UNAVAILABLE,
                        "Schema koleksiyonu bulunamadı.",
                        retryable=True,
                    )
                return {"ok": False, "collection": coll, "hits": [], "tables": [], "hint_extra": ""}
            sr = await client.post(f"{QDRANT_URL}/collections/{coll}/points/search", json=body)
            # If filter unsupported, retry without filter (legacy collections)
            if sr.status_code >= 400 and "filter" in body:
                body.pop("filter", None)
                sr = await client.post(f"{QDRANT_URL}/collections/{coll}/points/search", json=body)
            sr.raise_for_status()
            result = sr.json().get("result") or []
            # Neon/Postgres index has no status payload — drop status clause on empty hits
            if not result and isinstance(body.get("filter"), dict):
                must = list((body["filter"].get("must") or []))
                stripped = [m for m in must if m.get("key") != "status"]
                if len(stripped) < len(must):
                    body["filter"] = {"must": stripped} if stripped else None
                    if body["filter"] is None:
                        body.pop("filter", None)
                    sr = await client.post(
                        f"{QDRANT_URL}/collections/{coll}/points/search", json=body
                    )
                    sr.raise_for_status()
                    result = sr.json().get("result") or []
    except WorkflowError:
        raise
    except Exception as e:
        if fail_closed:
            raise WorkflowError(
                SCHEMA_RETRIEVAL_UNAVAILABLE,
                "Schema retrieval kullanılamıyor.",
                retryable=True,
            ) from e
        return {
            "ok": False,
            "collection": coll,
            "hits": [],
            "tables": [],
            "hint_extra": "",
            "error": str(e)[:200],
        }

    hits = []
    lines = [f"Retrieved schema context for datasource '{datasource_id}' (Qdrant {coll}):"]
    seen_tables: set[str] = set()
    # table_fq -> ordered unique column names (generic; filled from column hits + text)
    table_cols: dict[str, list[str]] = {}
    untrusted_comments: list[str] = []

    def _add_col(fq_name: str, col: str | None) -> None:
        c = str(col or "").strip().strip('"')
        if not fq_name or not c:
            return
        bucket = table_cols.setdefault(fq_name, [])
        if c not in bucket:
            bucket.append(c)

    def _cols_from_table_text(fq_name: str, body: str) -> None:
        """Parse 'Columns:\\n- name type' lines from table-level index docs."""
        if not fq_name or not body:
            return
        for m in re.finditer(r"(?m)^\s*-\s+([A-Za-z_][\w]*)\b", body):
            _add_col(fq_name, m.group(1))

    for hit in result:
        payload = hit.get("payload") or {}
        # Soft client-side tenant/datasource guard (fail closed for mismatches)
        p_ds = payload.get("datasource_id")
        p_tenant = payload.get("tenant_id")
        if p_ds and str(p_ds) != str(datasource_id):
            continue
        if p_tenant and tenant_id not in ("default", "") and str(p_tenant) != str(tenant_id):
            continue
        score = hit.get("score")
        text = str(payload.get("text") or "")[:500]
        table = payload.get("table")
        schema = payload.get("schema")
        kind = payload.get("kind")
        fq = f"{schema}.{table}" if schema and table else (table or "")
        if fq:
            seen_tables.add(str(fq))
        col_name = payload.get("column")
        if col_name:
            _add_col(str(fq), str(col_name))
        # Some indexers put columns[] on table docs
        for extra in payload.get("columns") or []:
            if isinstance(extra, str):
                _add_col(str(fq), extra)
            elif isinstance(extra, dict):
                _add_col(str(fq), extra.get("name") or extra.get("column"))
        if fq and str(kind or "").lower() in ("table", "view") and text:
            _cols_from_table_text(str(fq), text)
        comment = payload.get("comment") or payload.get("description")
        if comment:
            untrusted_comments.append(str(comment)[:300])
        hits.append(
            {
                "score": score,
                "kind": kind,
                "table": fq,
                "column": col_name,
                "text": text,
                "id": hit.get("id"),
            }
        )
        lines.append(f"- [{kind}] {fq} score={score:.3f}: {text[:220]}")

    # Dense per-table column block near the top of the hint so compact truncation keeps it.
    col_block: list[str] = []
    if table_cols:
        col_block.append("Authorized columns by table (use these names; do not invent):")
        for tname in sorted(table_cols.keys()):
            cols = table_cols[tname][:48]
            if cols:
                col_block.append(f"  {tname}: {', '.join(cols)}")

    if hits:
        header = lines[:1]
        hit_lines = lines[1:]
        hint = "\n".join(header + col_block + hit_lines)
    else:
        hint = ""
    return {
        "ok": True,
        "collection": coll,
        "hits": hits[:max_documents],
        "tables": sorted(seen_tables),
        "table_columns": {k: v[:48] for k, v in table_cols.items()},
        "hint_extra": hint,
        "untrusted_comments": untrusted_comments[:20],
        "filter": qfilter,
    }


def build_sanitized_context(
    *,
    question: str,
    schema_hint: str,
    retrieval: dict[str, Any],
    conversation_turns: list[dict[str, Any]] | None = None,
    semantic_context: str | None = None,
    planning_guidance: str | None = None,
) -> str:
    return sanitize_planning_context(
        question=question,
        schema_hint=schema_hint,
        retrieved_hint=str(retrieval.get("hint_extra") or ""),
        conversation_turns=conversation_turns,
        untrusted_comments=retrieval.get("untrusted_comments") or [],
        semantic_context=semantic_context,
        planning_guidance=planning_guidance,
    )
