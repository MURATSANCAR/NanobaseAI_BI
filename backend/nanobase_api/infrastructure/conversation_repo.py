"""Conversation + query plan persistence (bi_meta)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ConversationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def ensure_session(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        title: str = "Chat",
        datasource_id: str | None = None,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_tenants (id, name, status, created_at, updated_at)
                    VALUES (:id, :name, 'active', NOW(), NOW())
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {"id": tenant_id, "name": tenant_id},
            )
            payload = json.dumps({"datasource_id": datasource_id}, ensure_ascii=False)
            conn.execute(
                text(
                    """
                    INSERT INTO bi_chat_sessions (
                      session_id, tenant_id, project_id, title, message_count,
                      preview, payload_json, created_at, updated_at
                    ) VALUES (
                      :sid, :tenant_id, 'default', :title, 0, '', :payload, NOW(), NOW()
                    )
                    ON CONFLICT (tenant_id, session_id) DO UPDATE SET updated_at = NOW()
                    """
                ),
                {
                    "sid": conversation_id,
                    "tenant_id": tenant_id,
                    "title": (title or "Chat")[:256],
                    "payload": payload,
                },
            )

    def add_message(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        role: str,
        content: str,
        datasource_id: str | None = None,
        sql_text: str | None = None,
        execution_id: str | None = None,
    ) -> str:
        mid = str(uuid.uuid4())
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_conversation_messages (
                      id, tenant_id, conversation_id, role, content,
                      datasource_id, sql_text, execution_id, created_at
                    ) VALUES (
                      :id, :tenant_id, :cid, :role, :content,
                      :ds, :sql, :eid, NOW()
                    )
                    """
                ),
                {
                    "id": mid,
                    "tenant_id": tenant_id,
                    "cid": conversation_id,
                    "role": role,
                    "content": content,
                    "ds": datasource_id,
                    "sql": sql_text,
                    "eid": execution_id,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE bi_chat_sessions
                    SET message_count = message_count + 1,
                        preview = :preview,
                        updated_at = NOW()
                    WHERE tenant_id = :t AND session_id = :sid
                    """
                ),
                {
                    "preview": content[:512],
                    "t": tenant_id,
                    "sid": conversation_id,
                },
            )
        return mid

    def list_recent_messages(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        return self.list_messages(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            limit=limit,
        )

    def list_messages(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit or 200), 500))
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT role, content, sql_text, datasource_id, created_at
                    FROM bi_conversation_messages
                    WHERE tenant_id = :t AND conversation_id = :cid
                    ORDER BY created_at DESC
                    LIMIT :lim
                    """
                ),
                {"t": tenant_id, "cid": conversation_id, "lim": lim},
            ).mappings().all()
        out: list[dict[str, Any]] = []
        for r in reversed(list(rows)):
            item: dict[str, Any] = {
                "role": r["role"],
                "content": r["content"] or "",
            }
            sql_text = (r.get("sql_text") or "").strip()
            if sql_text and str(r.get("role") or "") != "user":
                item["meta"] = {
                    "sql": sql_text,
                    "session_id": conversation_id,
                    "db_name": r.get("datasource_id"),
                }
            out.append(item)
        return out

    def top_user_questions(
        self,
        *,
        tenant_id: str,
        datasource_id: str | None = None,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """Most-asked natural-language questions for a datasource (learning signal)."""
        lim = max(1, min(int(limit or 8), 20))
        ds = (datasource_id or "").strip() or None
        merged: dict[str, dict[str, Any]] = {}

        def _absorb(question: str, cnt: int, last_at: Any) -> None:
            q = (question or "").strip()
            if len(q) < 8:
                return
            key = " ".join(q.lower().split())[:240]
            if not key:
                return
            prev = merged.get(key)
            if prev is None:
                merged[key] = {"question": q, "count": int(cnt or 1), "last_at": last_at}
                return
            prev["count"] = int(prev["count"]) + int(cnt or 1)
            if last_at and (prev.get("last_at") is None or last_at > prev["last_at"]):
                prev["last_at"] = last_at
                prev["question"] = q

        with self._engine.connect() as conn:
            for r in conn.execute(
                text(
                    """
                    SELECT
                      MIN(question) AS question,
                      COUNT(*)::int AS cnt,
                      MAX(created_at) AS last_at
                    FROM bi_query_plans
                    WHERE tenant_id = :t
                      AND question IS NOT NULL
                      AND length(trim(question)) >= 8
                      AND (:ds IS NULL OR datasource_id = :ds)
                    GROUP BY lower(regexp_replace(trim(question), '\\s+', ' ', 'g'))
                    """
                ),
                {"t": tenant_id, "ds": ds},
            ).mappings():
                _absorb(str(r.get("question") or ""), int(r.get("cnt") or 1), r.get("last_at"))
            for r in conn.execute(
                text(
                    """
                    SELECT
                      MIN(content) AS question,
                      COUNT(*)::int AS cnt,
                      MAX(created_at) AS last_at
                    FROM bi_conversation_messages
                    WHERE tenant_id = :t
                      AND role = 'user'
                      AND length(trim(content)) >= 8
                      AND length(trim(content)) <= 280
                      AND (:ds IS NULL OR datasource_id = :ds)
                    GROUP BY lower(regexp_replace(trim(content), '\\s+', ' ', 'g'))
                    """
                ),
                {"t": tenant_id, "ds": ds},
            ).mappings():
                _absorb(str(r.get("question") or ""), int(r.get("cnt") or 1), r.get("last_at"))

        ranked = sorted(
            merged.values(),
            key=lambda x: (-int(x.get("count") or 0), x.get("last_at") or 0),
        )
        return [
            {"question": str(item["question"]).strip(), "count": int(item.get("count") or 1)}
            for item in ranked[:lim]
            if item.get("question")
        ]

    def save_plan(
        self,
        *,
        tenant_id: str,
        conversation_id: str,
        datasource_id: str,
        question: str,
        sql_text: str | None,
        dialect: str | None,
        execution_mode: str,
        executed: bool,
    ) -> str:
        pid = str(uuid.uuid4())
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO bi_query_plans (
                      id, tenant_id, conversation_id, datasource_id, question,
                      sql_text, dialect, execution_mode, executed, created_at
                    ) VALUES (
                      :id, :tenant_id, :cid, :ds, :q,
                      :sql, :dialect, :mode, :executed, NOW()
                    )
                    """
                ),
                {
                    "id": pid,
                    "tenant_id": tenant_id,
                    "cid": conversation_id,
                    "ds": datasource_id,
                    "q": question,
                    "sql": sql_text,
                    "dialect": dialect,
                    "mode": execution_mode,
                    "executed": executed,
                },
            )
        return pid
