"""002 — business_term + synonym tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_business_terms"
down_revision: Union[str, None] = "001_faz3_scans_conv"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _audit_cols():
    return [
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
    ]


def upgrade() -> None:
    op.create_table(
        "sc_business_term",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("language", sa.String(16), nullable=False, server_default="tr"),
        *_audit_cols(),
    )
    op.create_index("ix_sc_business_term_tenant_ds", "sc_business_term", ["tenant_id", "datasource_id"])
    op.create_index("ix_sc_business_term_norm", "sc_business_term", ["tenant_id", "datasource_id", "normalized_name"], unique=True)
    op.create_index("ix_sc_business_term_status", "sc_business_term", ["status"])

    op.create_table(
        "sc_business_term_synonym",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("business_term_id", sa.String(64), sa.ForeignKey("sc_business_term.id", ondelete="CASCADE"), nullable=False),
        sa.Column("synonym", sa.Text(), nullable=False),
        sa.Column("normalized_synonym", sa.String(256), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "ix_sc_bt_synonym_unique",
        "sc_business_term_synonym",
        ["tenant_id", "datasource_id", "normalized_synonym"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("sc_business_term_synonym")
    op.drop_table("sc_business_term")
