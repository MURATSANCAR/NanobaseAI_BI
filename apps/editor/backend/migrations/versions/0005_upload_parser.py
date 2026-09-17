"""Persist parser failures independently of transient API connections."""
from alembic import op
revision = '0005_upload_parser'
down_revision = '0004_operator_retry'
branch_labels = depends_on = None


def upgrade():
    op.execute('ALTER TABLE editor.uploads ADD COLUMN error_code text; ALTER TABLE editor.uploads ADD COLUMN finished_at timestamptz')


def downgrade():
    raise RuntimeError('Restore into a separate installation instead.')
