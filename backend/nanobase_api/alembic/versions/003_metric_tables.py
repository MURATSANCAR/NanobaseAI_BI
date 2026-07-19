"""003 — metric definition tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_metric_tables"
down_revision: Union[str, None] = "002_business_terms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sc_metric_definition",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("aggregation", sa.String(32), nullable=False),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("source_column", sa.Text(), nullable=False),
        sa.Column("null_policy", sa.String(16), nullable=False, server_default="ZERO"),
        sa.Column("time_field", sa.Text()),
        sa.Column("timezone", sa.String(64), server_default="Europe/Istanbul"),
        sa.Column("calendar_type", sa.String(32), server_default="CALENDAR"),
        sa.Column("default_granularity", sa.String(32), server_default="MONTH"),
        sa.Column("is_financial", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("multi_currency", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("currency_json", sa.Text()),
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
        "ix_sc_metric_code_unique",
        "sc_metric_definition",
        ["tenant_id", "datasource_id", "code"],
        unique=True,
    )
    op.create_index("ix_sc_metric_status", "sc_metric_definition", ["status"])

    op.create_table(
        "sc_metric_default_filter",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("metric_id", sa.String(64), sa.ForeignKey("sc_metric_definition.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filter_code", sa.String(128), nullable=False),
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
    op.drop_table("sc_metric_default_filter")
    op.drop_table("sc_metric_definition")
