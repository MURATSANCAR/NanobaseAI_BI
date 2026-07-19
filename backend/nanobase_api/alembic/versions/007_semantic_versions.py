"""007 — semantic_version + change + active pointer."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_semantic_versions"
down_revision: Union[str, None] = "006_verified_queries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sc_semantic_version",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("manifest_json", sa.Text()),
        sa.Column("manifest_sha256", sa.String(64)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("published_by", sa.String(128)),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", sa.String(128)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_by", sa.String(128)),
        sa.Column("asset_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
    )
    op.create_index(
        "ix_sc_semver_unique",
        "sc_semantic_version",
        ["tenant_id", "datasource_id", "version"],
        unique=True,
    )
    op.create_index(
        "ix_sc_semver_active",
        "sc_semantic_version",
        ["tenant_id", "datasource_id", "is_active"],
    )

    op.create_table(
        "sc_semantic_version_asset",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("semantic_version_id", sa.String(64), sa.ForeignKey("sc_semantic_version.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("asset_code", sa.String(128), nullable=False),
        sa.Column("asset_version", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
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
        "sc_semantic_change",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("semantic_version_id", sa.String(64), sa.ForeignKey("sc_semantic_version.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_kind", sa.String(16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("diff_json", sa.Text()),
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
    op.drop_table("sc_semantic_change")
    op.drop_table("sc_semantic_version_asset")
    op.drop_table("sc_semantic_version")
