"""Faz 3 additive tables: schema scans, conversation messages, query plans.

Uses nanobase_alembic_version — does not disturb existing bi_meta alembic (006_*).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_faz3_scans_conv"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bi_schema_scans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="QUEUED"),
        sa.Column("schema_count", sa.Integer()),
        sa.Column("table_count", sa.Integer()),
        sa.Column("column_count", sa.Integer()),
        sa.Column("relationship_count", sa.Integer()),
        sa.Column("indexed_document_count", sa.Integer()),
        sa.Column("skipped_document_count", sa.Integer()),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_bi_schema_scans_tenant_id", "bi_schema_scans", ["tenant_id"])
    op.create_index("ix_bi_schema_scans_datasource_id", "bi_schema_scans", ["datasource_id"])
    op.create_index("ix_bi_schema_scans_status", "bi_schema_scans", ["status"])

    op.create_table(
        "bi_conversation_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("datasource_id", sa.String(64)),
        sa.Column("sql_text", sa.Text()),
        sa.Column("execution_id", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_bi_conversation_messages_tenant_id", "bi_conversation_messages", ["tenant_id"])
    op.create_index(
        "ix_bi_conversation_messages_conversation_id",
        "bi_conversation_messages",
        ["conversation_id"],
    )

    op.create_table(
        "bi_query_plans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(128), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sql_text", sa.Text()),
        sa.Column("dialect", sa.String(32)),
        sa.Column("execution_mode", sa.String(32), nullable=False),
        sa.Column("executed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_bi_query_plans_tenant_id", "bi_query_plans", ["tenant_id"])
    op.create_index("ix_bi_query_plans_conversation_id", "bi_query_plans", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("bi_query_plans")
    op.drop_table("bi_conversation_messages")
    op.drop_table("bi_schema_scans")
