"""015 — sl_llm_queue: fair, time-ordered access to the shared language model."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "015_llm_queue"
down_revision: Union[str, None] = "014_semantic_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sl_llm_queue (
            id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            datasource_id VARCHAR(128) NOT NULL,
            user_id VARCHAR(128),
            purpose VARCHAR(64) NOT NULL,
            question TEXT,
            status VARCHAR(16) NOT NULL DEFAULT 'WAITING',
            enqueued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            heartbeat_at TIMESTAMPTZ,
            worker VARCHAR(128)
        );
        CREATE INDEX IF NOT EXISTS ix_sl_llm_queue_order ON sl_llm_queue (status, enqueued_at);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sl_llm_queue")
