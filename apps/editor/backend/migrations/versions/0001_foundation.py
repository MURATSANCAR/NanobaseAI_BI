"""Operational foundation only; book business schema is a separate P1 migration."""
from alembic import op

revision = '0001_foundation'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('''CREATE TABLE editor.deployments (
        release text PRIMARY KEY, installed_at timestamptz NOT NULL DEFAULT now())''')
    op.execute('''CREATE TABLE editor.worker_heartbeats (
        worker_id text PRIMARY KEY, release text NOT NULL,
        seen_at timestamptz NOT NULL DEFAULT now(), mode text NOT NULL)''')
    op.execute('''CREATE TABLE editor.source_probes (
        sha256 text PRIMARY KEY CHECK (sha256 ~ '^[a-f0-9]{64}$'),
        release text NOT NULL, manifest jsonb NOT NULL,
        recorded_at timestamptz NOT NULL DEFAULT now())''')
    op.execute('GRANT SELECT ON editor.deployments, editor.alembic_version TO editor_app')
    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON editor.worker_heartbeats TO editor_app')
    op.execute('GRANT SELECT, INSERT ON editor.source_probes TO editor_app')


def downgrade():
    raise RuntimeError('Use a verified backup in a separate installation; no destructive automatic downgrade.')
