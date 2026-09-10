"""017 — one row per concept sense.

upsert_concept finds-then-inserts under an in-process lock, which holds for one worker and not for two
processes: the nightly timer and a hand-run pipeline can both pass the lookup and each create the same
sense. The evidence for a term then splits between two rows and neither reaches the gate — the failure
is silent, and it looks like the catalog simply forgot something.

The constraint makes that a database error the store can catch and re-read, instead of a duplicate.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "017_concept_sense_unique"
down_revision: Union[str, None] = "016_profile_time_window"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sl_concept_sense
            ON sl_concept (tenant_id, datasource_id, normalized_term, semantic_type, sense_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sl_concept_sense")
