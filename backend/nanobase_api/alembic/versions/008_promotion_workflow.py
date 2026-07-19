"""008 — promotion workflow tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_promotion_workflow"
down_revision: Union[str, None] = "007_semantic_versions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sc_promotion_request",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("asset_id", sa.String(64), nullable=False),
        sa.Column("phase", sa.String(64), nullable=False, server_default="CANDIDATE"),
        sa.Column("requires_dual_approval", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("candidate_id", sa.String(64)),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
    )
    op.create_index("ix_sc_promotion_phase", "sc_promotion_request", ["phase"])

    op.create_table(
        "sc_promotion_review",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("promotion_request_id", sa.String(64), sa.ForeignKey("sc_promotion_request.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer_user_id", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
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
        "ix_sc_promotion_review_unique",
        "sc_promotion_review",
        ["promotion_request_id", "reviewer_user_id", "role"],
        unique=True,
    )

    op.create_table(
        "sc_promotion_decision",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("promotion_request_id", sa.String(64), sa.ForeignKey("sc_promotion_request.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(128), nullable=False),
        sa.Column("reason", sa.Text()),
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
        "sc_query_feedback",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("execution_id", sa.String(64)),
        sa.Column("feedback_type", sa.String(32), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("sql_fingerprint", sa.String(64)),
        sa.Column("semantic_version", sa.String(32)),
        sa.Column("candidate_id", sa.String(64)),
        sa.Column("comment", sa.Text()),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
    )


def downgrade() -> None:
    op.drop_table("sc_query_feedback")
    op.drop_table("sc_promotion_decision")
    op.drop_table("sc_promotion_review")
    op.drop_table("sc_promotion_request")
