"""005 — join_rule + join_condition tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_join_rules"
down_revision: Union[str, None] = "004_dimension_filter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sc_join_rule",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False),
        sa.Column("from_table", sa.Text(), nullable=False),
        sa.Column("to_table", sa.Text(), nullable=False),
        sa.Column("join_type", sa.String(16), nullable=False, server_default="INNER"),
        sa.Column("relationship", sa.String(32), nullable=False, server_default="MANY_TO_ONE"),
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
        "ix_sc_join_code_unique",
        "sc_join_rule",
        ["tenant_id", "datasource_id", "code"],
        unique=True,
    )

    op.create_table(
        "sc_join_condition",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("join_rule_id", sa.String(64), sa.ForeignKey("sc_join_rule.id", ondelete="CASCADE"), nullable=False),
        sa.Column("left_expr", sa.Text(), nullable=False),
        sa.Column("operator", sa.String(16), nullable=False, server_default="="),
        sa.Column("right_expr", sa.Text(), nullable=False),
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
    op.drop_table("sc_join_condition")
    op.drop_table("sc_join_rule")
