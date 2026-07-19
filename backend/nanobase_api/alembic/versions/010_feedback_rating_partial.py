"""010 — allow partial feedback rating (0) on bi_query_feedback."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "010_feedback_rating_partial"
down_revision: Union[str, None] = "009_semantic_dependencies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE bi_query_feedback DROP CONSTRAINT IF EXISTS bi_query_feedback_rating_check")
    op.execute(
        "ALTER TABLE bi_query_feedback ADD CONSTRAINT bi_query_feedback_rating_check "
        "CHECK (rating IN (-1, 0, 1))"
    )


def downgrade() -> None:
    op.execute("DELETE FROM bi_query_feedback WHERE rating = 0")
    op.execute("ALTER TABLE bi_query_feedback DROP CONSTRAINT IF EXISTS bi_query_feedback_rating_check")
    op.execute(
        "ALTER TABLE bi_query_feedback ADD CONSTRAINT bi_query_feedback_rating_check "
        "CHECK (rating IN (-1, 1))"
    )
