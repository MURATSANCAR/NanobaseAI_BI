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
