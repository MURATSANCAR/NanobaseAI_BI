"""Faz 7 semantic catalog + verified SQL + feedback API helpers."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


def norm_question(q: str) -> str:
    q = (q or "").lower().strip()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[^\w\sçğıöşüâîû]", "", q, flags=re.I)
    return q


def lookup_verified_sql(engine: Engine, question: str, datasource_id: str) -> Optional[dict[str, Any]]:
    """Legacy physical SQL cache — disabled for production retrieval (Kural 4).

    STALE/legacy rows are never returned. Prefer semantic_catalog logical plans.
    """
    _ = (engine, question, datasource_id)
    return None


def list_glossary(engine: Engine, tenant_id: str = "default") -> list[dict[str, Any]]:
    """FE shape: BiGlossaryEntry { id, table, column, business_name, definition, ... }."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, term, table_name, column_name, definition, status, payload_json
                FROM bi_glossary_entries
                WHERE tenant_id = :t
                ORDER BY term
                """
            ),
            {"t": tenant_id},
        ).mappings()
        out = []
        for r in rows:
            payload = json.loads(r["payload_json"] or "{}")
            out.append(
                {
                    "id": r["id"],
                    "table": r["table_name"] or "",
                    "column": r["column_name"],
                    "business_name": r["term"],
                    "definition": r["definition"] or "",
                    "synonyms": payload.get("synonyms") or [],
                    "source": payload.get("datasource_id") or "bi_meta",
                    "status": r["status"],
                }
            )
        return out


def list_metrics(engine: Engine, tenant_id: str = "default") -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT metric_id, label, expression, source_table, status, golden_sql, owner
                FROM bi_metrics
                WHERE tenant_id = :t
                ORDER BY label
                """
            ),
            {"t": tenant_id},
        ).mappings()
        return [
            {
                "metric_id": r["metric_id"],
                "label": r["label"],
                "expression": r["expression"],
                "source_table": r["source_table"],
                "status": r["status"],
                "golden_sql": r["golden_sql"],
                "owner": r["owner"],
            }
            for r in rows
        ]


def list_joins(engine: Engine, tenant_id: str = "default") -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT join_id, left_table, right_table, left_key, right_key, cardinality
                FROM bi_joins WHERE tenant_id = :t ORDER BY join_id
                """
            ),
            {"t": tenant_id},
        ).mappings()
        return [dict(r) for r in rows]


def save_feedback(
    engine: Engine,
    *,
    datasource_id: str,
    question: str,
    rating: int,
    sql_text: str | None = None,
    session_id: str | None = None,
    comment: str | None = None,
    promote_verified: bool = False,
    tenant_id: str = "default",
) -> dict[str, Any]:
    fid = f"fb-{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    candidate_id = None
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO bi_query_feedback
                  (id, tenant_id, datasource_id, session_id, question, sql_text, rating, comment, promote_verified, created_at)
                VALUES
                  (:id, :tenant, :ds, :sid, :q, :sql, :rating, :comment, :promote, :now)
                """
            ),
            {
                "id": fid,
                "tenant": tenant_id,
                "ds": datasource_id,
                "sid": session_id,
                "q": question,
                "sql": sql_text,
                "rating": rating,
                "comment": comment,
                "promote": promote_verified,
                "now": now,
            },
        )
        # Kural 2: Feedback asla otomatik verified SQL yazmaz.
        # Yalnız rating == 1 (doğru) candidate üretebilir; kısmi/yanlış promote etmez.
        if rating == 1 and sql_text:
            try:
                from nanobase_api.semantic_catalog.application.services import (
                    create_candidate_from_feedback,
                )
                from nanobase_api.semantic_catalog.infrastructure.catalog_store import (
                    get_catalog_store,
                )

                cand = create_candidate_from_feedback(
                    get_catalog_store(),
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    question=question,
                    logical_plan={"metric": None, "legacySqlFingerprint": True},
                    user_id="feedback",
                    sql_fingerprint=norm_question(question)[:64],
                )
                candidate_id = cand.id
            except Exception:
                candidate_id = None
    return {
        "ok": True,
        "feedback_id": fid,
        "verified_sql_id": None,
        "candidate_id": candidate_id,
        "auto_promote_disabled": True,
    }


def semantic_status(engine: Engine, tenant_id: str = "default") -> dict[str, Any]:
    with engine.connect() as conn:
        g = conn.execute(
            text("SELECT count(*) FROM bi_glossary_entries WHERE tenant_id=:t"), {"t": tenant_id}
        ).scalar()
        m = conn.execute(text("SELECT count(*) FROM bi_metrics WHERE tenant_id=:t"), {"t": tenant_id}).scalar()
        j = conn.execute(text("SELECT count(*) FROM bi_joins WHERE tenant_id=:t"), {"t": tenant_id}).scalar()
        v = conn.execute(text("SELECT count(*) FROM bi_verified_sql WHERE status='verified'")).scalar()
    return {
        "ok": True,
        "enabled": True,
        "engine": "nanobase_api",
        "glossary": int(g or 0),
        "metrics": int(m or 0),
        "joins": int(j or 0),
        "verified_sql": int(v or 0),
    }
