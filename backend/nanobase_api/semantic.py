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
    qn = norm_question(question)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, question_display, sql_text, hit_count
                FROM bi_verified_sql
                WHERE datasource_id = :ds AND status = 'verified' AND question_norm = :qn
                LIMIT 1
                """
            ),
            {"ds": datasource_id, "qn": qn},
        ).mappings().first()
        if not row:
            # soft contains match on short questions
            rows = conn.execute(
                text(
                    """
                    SELECT id, question_display, sql_text, hit_count, question_norm
                    FROM bi_verified_sql
                    WHERE datasource_id = :ds AND status = 'verified'
                    ORDER BY hit_count DESC
                    LIMIT 50
                    """
                ),
                {"ds": datasource_id},
            ).mappings().all()
            for r in rows:
                rn = r["question_norm"]
                if qn == rn or qn in rn or rn in qn:
                    row = r
                    break
        if not row:
            return None
        conn.execute(
            text(
                "UPDATE bi_verified_sql SET hit_count = hit_count + 1, updated_at = :now WHERE id = :id"
            ),
            {"now": datetime.now(timezone.utc), "id": row["id"]},
        )
        conn.commit()
        return {
            "id": row["id"],
            "question": row["question_display"],
            "sql": row["sql_text"],
            "hit_count": int(row["hit_count"]) + 1,
            "source": "verified_sql",
        }


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
        verified_id = None
        if promote_verified and rating == 1 and sql_text:
            verified_id = f"vsql-{uuid.uuid5(uuid.NAMESPACE_URL, norm_question(question) + sql_text).hex[:12]}"
            conn.execute(
                text(
                    """
                    INSERT INTO bi_verified_sql
                      (id, tenant_id, datasource_id, question_norm, question_display, sql_text, status, created_by, created_at, updated_at)
                    VALUES
                      (:id, :tenant, :ds, :qn, :qd, :sql, 'verified', 'feedback', :now, :now)
                    ON CONFLICT (id) DO UPDATE SET
                      sql_text = EXCLUDED.sql_text,
                      status = 'verified',
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": verified_id,
                    "tenant": tenant_id,
                    "ds": datasource_id,
                    "qn": norm_question(question),
                    "qd": question,
                    "sql": sql_text,
                    "now": now,
                },
            )
    return {"ok": True, "feedback_id": fid, "verified_sql_id": verified_id}


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
