"""019 — sl_suggestion: what the system read out of the schema, before anyone has confirmed it.

Tens of thousands of columns nobody has ever named will not be described by waiting. The system reads
the table name, the column name and the values in it and writes down what they look like they mean —
as a suggestion, filed apart from definitions, that a person accepts or corrects. Accepting is what
turns it into a definition; on its own it never passes the gate.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "019_suggestions"
down_revision: Union[str, None] = "018_profile_per_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sl_suggestion (
            id VARCHAR(64) PRIMARY KEY,
            datasource_id VARCHAR(128) NOT NULL,
            table_pattern VARCHAR(256) NOT NULL,
            column_name VARCHAR(128),
            text TEXT NOT NULL,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
            model VARCHAR(64),
            status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sl_suggestion_target
            ON sl_suggestion (datasource_id, table_pattern, column_name);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sl_suggestion")
