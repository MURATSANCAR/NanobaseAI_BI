"""009 — semantic dependency + validation run + publish lock."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009_semantic_dependencies"
down_revision: Union[str, None] = "008_promotion_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sc_semantic_dependency",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("from_type", sa.String(32), nullable=False),
        sa.Column("from_code", sa.String(128), nullable=False),
        sa.Column("to_kind", sa.String(32), nullable=False),
        sa.Column("to_ref", sa.Text(), nullable=False),
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
        "ix_sc_dep_to",
        "sc_semantic_dependency",
        ["tenant_id", "datasource_id", "to_kind", "to_ref"],
    )
    op.create_index(
        "ix_sc_dep_from",
        "sc_semantic_dependency",
        ["tenant_id", "datasource_id", "from_type", "from_code"],
    )

    op.create_table(
        "sc_semantic_validation_run",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("asset_id", sa.String(64), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("report_json", sa.Text()),
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
        "sc_publish_lock",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("lock_kind", sa.String(32), nullable=False),
        sa.Column("holder", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.String(128)),
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
        "ix_sc_publish_lock_unique",
        "sc_publish_lock",
        ["tenant_id", "datasource_id", "lock_kind"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("sc_publish_lock")
    op.drop_table("sc_semantic_validation_run")
    op.drop_table("sc_semantic_dependency")
