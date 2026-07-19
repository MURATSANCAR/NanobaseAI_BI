"""006 — verified question / candidate / query / baseline."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_verified_queries"
down_revision: Union[str, None] = "005_join_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sc_verified_question",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("normalized_intent_json", sa.Text(), nullable=False),
        sa.Column("intent_fingerprint", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
    )
    op.create_index(
        "ix_sc_vq_intent",
        "sc_verified_question",
        ["tenant_id", "datasource_id", "intent_fingerprint"],
    )

    op.create_table(
        "sc_verified_query_candidate",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("logical_plan_json", sa.Text(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("sql_fingerprint", sa.String(64)),
        sa.Column("execution_id", sa.String(64)),
        sa.Column("candidate_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
    )

    op.create_table(
        "sc_verified_query",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("verified_question_id", sa.String(64), sa.ForeignKey("sc_verified_question.id"), nullable=False),
        sa.Column("semantic_version", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("dialect", sa.String(32), nullable=False, server_default="postgres"),
        sa.Column("logical_plan_json", sa.Text(), nullable=False),
        sa.Column("compiled_sql", sa.Text()),
        sa.Column("expected_result_fingerprint", sa.String(128)),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
    )
    op.create_index("ix_sc_verified_query_status", "sc_verified_query", ["status"])

    op.create_table(
        "sc_verified_query_execution_baseline",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("verified_query_id", sa.String(64), sa.ForeignKey("sc_verified_query.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result_fingerprint", sa.String(128), nullable=False),
        sa.Column("row_count", sa.Integer()),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
    )

    # Deprecate legacy auto-promote path when legacy table exists
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.bi_verified_sql') IS NOT NULL THEN
            UPDATE bi_verified_sql SET status = 'STALE' WHERE status = 'verified';
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF to_regclass('public.bi_verified_sql') IS NOT NULL THEN
            UPDATE bi_verified_sql SET status = 'verified' WHERE status = 'STALE';
          END IF;
        END $$;
        """
    )
    op.drop_table("sc_verified_query_execution_baseline")
    op.drop_table("sc_verified_query")
    op.drop_table("sc_verified_query_candidate")
    op.drop_table("sc_verified_question")
