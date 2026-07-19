"""SQLAlchemy models for Faz 3 additive tables (bi_meta)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SchemaScanModel(Base):
    __tablename__ = "bi_schema_scans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    datasource_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    schema_count: Mapped[Optional[int]] = mapped_column(Integer)
    table_count: Mapped[Optional[int]] = mapped_column(Integer)
    column_count: Mapped[Optional[int]] = mapped_column(Integer)
    relationship_count: Mapped[Optional[int]] = mapped_column(Integer)
    indexed_document_count: Mapped[Optional[int]] = mapped_column(Integer)
    skipped_document_count: Mapped[Optional[int]] = mapped_column(Integer)
    error: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConversationMessageModel(Base):
    __tablename__ = "bi_conversation_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    datasource_id: Mapped[Optional[str]] = mapped_column(String(64))
    sql_text: Mapped[Optional[str]] = mapped_column(Text)
    execution_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QueryPlanModel(Base):
    __tablename__ = "bi_query_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    datasource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    sql_text: Mapped[Optional[str]] = mapped_column(Text)
    dialect: Mapped[Optional[str]] = mapped_column(String(32))
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    executed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
