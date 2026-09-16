"""Bounded automatic attempts with an audited operator recovery action."""
from alembic import op
revision='0004_operator_retry'
down_revision='0003_question_jobs'
branch_labels=depends_on=None


def upgrade():
    op.execute('ALTER TABLE editor.jobs ADD COLUMN max_attempts integer NOT NULL DEFAULT 3 CHECK(max_attempts>0)')


def downgrade():
    raise RuntimeError('Use an isolated restore.')
