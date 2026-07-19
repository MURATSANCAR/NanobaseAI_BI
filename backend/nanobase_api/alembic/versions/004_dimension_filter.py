"""004 — dimension + filter_rule tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_dimension_filter"
down_revision: Union[str, None] = "003_metric_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sc_filter_rule",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("expression_json", sa.Text(), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        "ix_sc_filter_code_unique",
        "sc_filter_rule",
        ["tenant_id", "datasource_id", "code"],
        unique=True,
    )

    op.create_table(
        "sc_dimension_definition",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("source_column", sa.Text(), nullable=False),
        sa.Column("join_rule_code", sa.String(128)),
        sa.Column("cardinality", sa.String(16), nullable=False, server_default="LOW"),
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
        "ix_sc_dimension_code_unique",
        "sc_dimension_definition",
        ["tenant_id", "datasource_id", "code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("sc_dimension_definition")
    op.drop_table("sc_filter_rule")
