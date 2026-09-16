"""Queued questions and content-checked upload sessions."""
from alembic import op
revision='0003_question_jobs'
down_revision='0002_book_pipeline'
branch_labels=depends_on=None


def upgrade():
    op.execute('''ALTER TABLE editor.jobs ADD COLUMN task text NOT NULL DEFAULT 'analysis';
    ALTER TABLE editor.jobs ADD COLUMN payload jsonb NOT NULL DEFAULT '{}';
    CREATE TABLE editor.uploads (
      id uuid PRIMARY KEY, edition_id uuid NOT NULL REFERENCES editor.editions,
      expected_bytes bigint NOT NULL CHECK(expected_bytes>0 AND expected_bytes<=52428800),
      expected_sha256 text NOT NULL, status text NOT NULL DEFAULT 'CREATED',
      content_version_id uuid REFERENCES editor.content_versions,
      created_at timestamptz NOT NULL DEFAULT now());
    GRANT SELECT,INSERT,UPDATE ON editor.uploads TO editor_app;''')


def downgrade():
    raise RuntimeError('Use a verified isolated restore.')
