"""Authorized schema retrieval with tenant/datasource filters."""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Iterable

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


def _fold_ident(s: str) -> str:
    """ASCII-fold for index matching (müşteri ↔ musteri) without synonym catalogs."""
    text = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _bare_table(name: str) -> str:
    t = (name or "").strip().strip('"').lower()
    return t.rsplit(".", 1)[-1] if t else ""


def parse_missing_tables_from_error(message: str) -> list[str]:
    """Extract table identifiers from TABLE_OR_VIEW_NOT_FOUND-style messages."""
    msg = message or ""
    found: list[str] = []
    m = re.search(r"referans[ıi]\s*:\s*([^.]+)", msg, flags=re.I)
    if m:
        for part in re.split(r"[,;]", m.group(1)):
            t = part.strip().strip('"').strip("'")
            if t and re.match(r"^[A-Za-z_][\w.]{1,120}$", t):
                found.append(t)
    if not found:
        for m2 in re.finditer(r"\b([A-Za-z_][\w]*\.[A-Za-z_][\w]*)\b", msg):
            found.append(m2.group(1))
    out: list[str] = []
    seen: set[str] = set()
    for t in found:
        key = t.lower()
        if key in seen or len(_bare_table(t)) < 2:
            continue
        seen.add(key)
        out.append(t)
    return out[:12]


def _table_name_matches(missing: str, indexed_fq: str) -> bool:
    """Match missing SQL ref to an indexed fq name without synonym dictionaries."""
    miss_bare = _bare_table(missing)
    idx_bare = _bare_table(indexed_fq)
    if not miss_bare or not idx_bare:
        return False
    if miss_bare == idx_bare:
        return True
    if missing.lower() == indexed_fq.lower():
        return True
    mf, iff = _fold_ident(miss_bare), _fold_ident(idx_bare)
    if mf == iff:
        return True
    # Substring only when both sides are reasonably long (avoid 'sip' → random).
    if len(mf) >= 5 and (mf in iff or iff in mf):
        return True
    return False


def _merge_col(
    table_cols: dict[str, list[str]],
    table_types: dict[str, dict[str, str]],
    fq_name: str,
    col: str | None,
    typ: str | None = None,
) -> None:
    c = str(col or "").strip().strip('"')
    if not fq_name or not c:
        return
    bucket = table_cols.setdefault(fq_name, [])
    if c not in bucket:
        bucket.append(c)
    t = str(typ or "").strip()
    if t:
        table_types.setdefault(fq_name, {})[c.lower()] = t


def _cols_from_table_text(
    table_cols: dict[str, list[str]],
    table_types: dict[str, dict[str, str]],
    fq_name: str,
    body: str,
) -> None:
    if not fq_name or not body:
        return
    for m in re.finditer(
        r"(?m)^\s*-\s+([A-Za-z_][\w]*)\b(?:\s+([A-Za-z][\w\s()]+?))?\s*$",
        body,
    ):
        _merge_col(table_cols, table_types, fq_name, m.group(1), (m.group(2) or "").strip() or None)


def _build_hint(
    *,
    datasource_id: str,
    coll: str,
    hits: list[dict[str, Any]],
    table_cols: dict[str, list[str]],
    table_types: dict[str, dict[str, str]],
) -> str:
    lines = [f"Retrieved schema context for datasource '{datasource_id}' (Qdrant {coll}):"]
    col_block: list[str] = []
    if table_cols:
        col_block.append("Authorized columns by table (use these names; do not invent):")
        for tname in sorted(table_cols.keys()):
            cols = table_cols[tname][:48]
            if cols:
                col_block.append(f"  {tname}: {', '.join(cols)}")
    type_block: list[str] = []
    if table_types:
        type_block.append("Column types by table (do not cast non-date columns to date):")
        for tname in sorted(table_types.keys())[:24]:
            pairs = [
                f"{c}:{table_types[tname][c]}"
                for c in list(table_types[tname])[:16]
            ]
            if pairs:
                type_block.append(f"  {tname}: {', '.join(pairs)}")
    hit_lines = [
        f"- [{h.get('kind')}] {h.get('table')} score={float(h.get('score') or 0):.3f}: "
        f"{str(h.get('text') or '')[:220]}"
        for h in hits
    ]
    if hits or col_block:
        return "\n".join(lines + col_block + type_block + hit_lines)
    return ""


def _ingest_payload(
    payload: dict[str, Any],
    *,
    datasource_id: str,
    tenant_id: str,
    seen_tables: set[str],
    table_cols: dict[str, list[str]],
    table_types: dict[str, dict[str, str]],
    score: float | None = None,
) -> dict[str, Any] | None:
    p_ds = payload.get("datasource_id")
    p_tenant = payload.get("tenant_id")
    if p_ds and str(p_ds) != str(datasource_id):
        return None
    if p_tenant and tenant_id not in ("default", "") and str(p_tenant) != str(tenant_id):
        return None
    text = str(payload.get("text") or "")[:500]
    table = payload.get("table")
    schema = payload.get("schema")
    kind = payload.get("kind")
    fq = f"{schema}.{table}" if schema and table else (table or "")
    if fq:
        seen_tables.add(str(fq))
    col_name = payload.get("column")
    typ = (
        payload.get("type_display")
        or payload.get("data_type")
        or payload.get("udt_name")
        or payload.get("type")
    )
    if col_name:
        _merge_col(table_cols, table_types, str(fq), str(col_name), str(typ) if typ else None)
    for extra in payload.get("columns") or []:
        if isinstance(extra, str):
            _merge_col(table_cols, table_types, str(fq), extra)
        elif isinstance(extra, dict):
            _merge_col(
                table_cols,
                table_types,
                str(fq),
                extra.get("name") or extra.get("column"),
                extra.get("type_display") or extra.get("data_type") or extra.get("type"),
            )
    if fq and str(kind or "").lower() in ("table", "view") and text:
        _cols_from_table_text(table_cols, table_types, str(fq), text)
    return {
        "score": score,
        "kind": kind,
        "table": fq,
        "column": col_name,
        "text": text,
    }


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

    hits: list[dict[str, Any]] = []
    seen_tables: set[str] = set()
    table_cols: dict[str, list[str]] = {}
    table_types: dict[str, dict[str, str]] = {}
    untrusted_comments: list[str] = []

    for hit in result:
        payload = hit.get("payload") or {}
        ingested = _ingest_payload(
            payload,
            datasource_id=datasource_id,
            tenant_id=tenant_id,
            seen_tables=seen_tables,
            table_cols=table_cols,
            table_types=table_types,
            score=hit.get("score"),
        )
        if not ingested:
            continue
        comment = payload.get("comment") or payload.get("description")
        if comment:
            untrusted_comments.append(str(comment)[:300])
        ingested["id"] = hit.get("id")
        hits.append(ingested)

    hint = _build_hint(
        datasource_id=datasource_id,
        coll=coll,
        hits=hits,
        table_cols=table_cols,
        table_types=table_types,
    )
    return {
        "ok": True,
        "collection": coll,
        "hits": hits[:max_documents],
        "tables": sorted(seen_tables),
        "table_columns": {k: v[:48] for k, v in table_cols.items()},
        "table_column_types": {
            k: dict(list(v.items())[:48]) for k, v in table_types.items()
        },
        "hint_extra": hint,
        "untrusted_comments": untrusted_comments[:20],
        "filter": qfilter,
    }


async def expand_tables_from_index(
    missing_tables: Iterable[str],
    *,
    tenant_id: str,
    datasource_id: str,
    existing: dict[str, Any] | None = None,
    scroll_limit: int = 256,
) -> dict[str, Any]:
    """Pull missing tables from the schema index (no static synonym catalogs).

    Matches bare/FQ names against indexed ``schema.table`` payloads via exact,
    ASCII-fold, and long-substring equality. Merges into ``existing`` retrieval.
    """
    missing = [str(t).strip() for t in (missing_tables or []) if str(t).strip()]
    base = dict(existing or {})
    if not missing:
        return {**base, "expanded_tables": [], "ok": bool(base.get("ok"))}

    coll = collection_for(datasource_id)
    qfilter = build_qdrant_filter(tenant_id=tenant_id, datasource_id=datasource_id)

    try:
        body: dict[str, Any] = {
            "limit": min(int(scroll_limit), 512),
            "with_payload": True,
            "with_vector": False,
        }
        if qfilter:
            body["filter"] = qfilter
        async with httpx.AsyncClient(timeout=30.0) as client:
            sr = await client.post(
                f"{QDRANT_URL}/collections/{coll}/points/scroll", json=body
            )
            if sr.status_code >= 400 and "filter" in body:
                body.pop("filter", None)
                sr = await client.post(
                    f"{QDRANT_URL}/collections/{coll}/points/scroll", json=body
                )
            if sr.status_code >= 400:
                return {**base, "expanded_tables": [], "expand_error": f"scroll_{sr.status_code}"}
            points = (sr.json().get("result") or {}).get("points") or []
    except Exception as e:  # noqa: BLE001
        return {**base, "expanded_tables": [], "expand_error": str(e)[:200]}

    # Build a scratch index from scroll — do not merge whole collection yet.
    idx_tables: set[str] = set()
    idx_cols: dict[str, list[str]] = {}
    idx_types: dict[str, dict[str, str]] = {}
    idx_hits: list[dict[str, Any]] = []
    for pt in points:
        payload = pt.get("payload") or {}
        ingested = _ingest_payload(
            payload,
            datasource_id=datasource_id,
            tenant_id=tenant_id,
            seen_tables=idx_tables,
            table_cols=idx_cols,
            table_types=idx_types,
            score=None,
        )
        if ingested:
            ingested["id"] = pt.get("id")
            idx_hits.append(ingested)

    expanded: list[str] = []
    for miss in missing:
        for fq in sorted(idx_tables):
            if _table_name_matches(miss, fq):
                if fq not in expanded:
                    expanded.append(fq)
                break

    if not expanded:
        return {**base, "expanded_tables": [], "ok": bool(base.get("ok")), "collection": coll}

    seen_tables: set[str] = set(str(t) for t in (base.get("tables") or [])) | set(expanded)
    table_cols: dict[str, list[str]] = {
        str(k): list(v) for k, v in (base.get("table_columns") or {}).items()
    }
    table_types: dict[str, dict[str, str]] = {
        str(k): {str(ck).lower(): str(cv) for ck, cv in (v or {}).items()}
        for k, v in (base.get("table_column_types") or {}).items()
    }
    for fq in expanded:
        for c in idx_cols.get(fq) or []:
            _merge_col(table_cols, table_types, fq, c, (idx_types.get(fq) or {}).get(c.lower()))
        for c, typ in (idx_types.get(fq) or {}).items():
            _merge_col(table_cols, table_types, fq, c, typ)

    base_hits = list(base.get("hits") or [])
    add_hits = [h for h in idx_hits if str(h.get("table") or "") in set(expanded)]
    slim_hits = (base_hits + add_hits)[:80]
    hint = _build_hint(
        datasource_id=datasource_id,
        coll=coll,
        hits=slim_hits,
        table_cols=table_cols,
        table_types=table_types,
    )
    return {
        **base,
        "ok": True,
        "collection": coll,
        "hits": slim_hits,
        "tables": sorted(seen_tables),
        "table_columns": {k: v[:48] for k, v in table_cols.items()},
        "table_column_types": {
            k: dict(list(v.items())[:48]) for k, v in table_types.items()
        },
        "hint_extra": hint,
        "expanded_tables": expanded,
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
