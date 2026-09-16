"""Durable, scoped book runs and append-only outputs."""
from alembic import op

revision = '0002_book_pipeline'
down_revision = '0001_foundation'
branch_labels = depends_on = None


def upgrade():
    op.execute('''
    CREATE TABLE editor.works (
      id uuid PRIMARY KEY, title text NOT NULL, owner_id text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE editor.editions (
      id uuid PRIMARY KEY, work_id uuid NOT NULL REFERENCES editor.works,
      label text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE editor.content_versions (
      id uuid PRIMARY KEY, edition_id uuid NOT NULL REFERENCES editor.editions,
      sha256 text NOT NULL REFERENCES editor.source_probes,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(edition_id,sha256));
    CREATE TABLE editor.generations (
      id uuid PRIMARY KEY, content_version_id uuid NOT NULL REFERENCES editor.content_versions,
      status text NOT NULL DEFAULT 'BUILDING', manifest jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE editor.jobs (
      id uuid PRIMARY KEY, generation_id uuid NOT NULL REFERENCES editor.generations,
      status text NOT NULL DEFAULT 'QUEUED', owner_id uuid,
      lease_until timestamptz, attempt_no integer NOT NULL DEFAULT 0,
      fencing_token bigint NOT NULL DEFAULT 0, cancellation_requested boolean NOT NULL DEFAULT false,
      progress jsonb NOT NULL DEFAULT '{}', error_code text,
      created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz);
    CREATE TABLE editor.records (
      id uuid PRIMARY KEY, generation_id uuid NOT NULL REFERENCES editor.generations,
      kind text NOT NULL, record_key text NOT NULL, data jsonb NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(generation_id,kind,record_key));
    CREATE INDEX ON editor.records(generation_id,kind);
    CREATE TABLE editor.outbox (
      id uuid PRIMARY KEY REFERENCES editor.records, generation_id uuid NOT NULL REFERENCES editor.generations,
      delivered_at timestamptz);
    CREATE TABLE editor.reviews (
      id uuid PRIMARY KEY, generation_id uuid NOT NULL REFERENCES editor.generations,
      target_id uuid NOT NULL REFERENCES editor.records, actor_id text NOT NULL,
      decision text NOT NULL, reason text NOT NULL, version integer NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(target_id,version));
    CREATE TABLE editor.idempotency (
      actor_id text NOT NULL, key text NOT NULL, request_hash text NOT NULL,
      response jsonb NOT NULL, PRIMARY KEY(actor_id,key));
    GRANT SELECT, INSERT, UPDATE ON editor.works, editor.editions, editor.content_versions,
      editor.generations, editor.jobs, editor.records, editor.outbox, editor.reviews, editor.idempotency TO editor_app;
    ''')


def downgrade():
    raise RuntimeError('Restore into a separate installation instead.')
