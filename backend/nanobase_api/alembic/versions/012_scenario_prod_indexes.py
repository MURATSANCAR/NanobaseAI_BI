"""012 — scenario engine production indexes (published paraphrase hash uniqueness)."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "012_scenario_prod_indexes"
down_revision: Union[str, None] = "011_scenario_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_sc_scenario_paraphrase_published_hash
        ON sc_scenario_paraphrase (tenant_id, datasource_id, normalized_question_hash)
        WHERE status = 'PUBLISHED'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_sc_scenario_instance_generator
        ON sc_scenario_instance (datasource_id, schema_version, generator_version, status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_sc_scenario_instance_generator")
    op.execute("DROP INDEX IF EXISTS uq_sc_scenario_paraphrase_published_hash")
