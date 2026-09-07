"""018 — a schema profile is one physical table, not one name pattern.

A logical entity often lives in several tables that share a naming pattern and differ only in context:
one per fiscal period is the common case. Keying the profile on the pattern made those tables overwrite
each other, so only the period profiled last survived and every earlier year became invisible — the
data was there and nothing could reach it.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "018_profile_per_table"
down_revision: Union[str, None] = "017_concept_sense_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE sl_schema_profile DROP CONSTRAINT IF EXISTS uq_sl_schema_profile")
    op.execute("DROP INDEX IF EXISTS uq_sl_schema_profile")
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS uq_sl_schema_profile_table
               ON sl_schema_profile (datasource_id, table_name)"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sl_schema_profile_table")
