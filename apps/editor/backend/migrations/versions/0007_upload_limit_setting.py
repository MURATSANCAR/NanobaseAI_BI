"""Upload size is a configured limit, not a schema constant.

The API and the parser enforce EDITOR_MAX_SOURCE_BYTES; a fixed upper bound in
the table check duplicated the default and silently overrode the setting.
"""
from alembic import op
revision='0007_upload_limit_setting'
down_revision='0006_book_access'
branch_labels=depends_on=None


def upgrade():
    op.execute('''
    ALTER TABLE editor.uploads DROP CONSTRAINT IF EXISTS uploads_expected_bytes_check;
    ALTER TABLE editor.uploads ADD CONSTRAINT uploads_expected_bytes_check CHECK(expected_bytes>0);
    ''')


def downgrade():
    op.execute('''
    ALTER TABLE editor.uploads DROP CONSTRAINT IF EXISTS uploads_expected_bytes_check;
    ALTER TABLE editor.uploads ADD CONSTRAINT uploads_expected_bytes_check CHECK(expected_bytes>0 AND expected_bytes<=52428800);
    ''')
