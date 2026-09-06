"""016 — sl_schema_profile.time_window_json: the measured first/last date of each entity.

The column belongs to 015 by intent, but a deployment that already applied 015 will never run it
again, so it gets its own forward-only revision instead of an edit to an applied one.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "016_profile_time_window"
down_revision: Union[str, None] = "015_llm_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE sl_schema_profile ADD COLUMN IF NOT EXISTS time_window_json JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE sl_schema_profile DROP COLUMN IF EXISTS time_window_json")
