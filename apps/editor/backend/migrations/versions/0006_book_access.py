"""User and book permissions; scoped credentials are stored only as hashes."""
from alembic import op
revision='0006_book_access'
down_revision='0005_upload_parser'
branch_labels=depends_on=None


def upgrade():
    op.execute('''
    CREATE TABLE editor.users (
      id text PRIMARY KEY, display_name text NOT NULL,
      system_role text NOT NULL CHECK(system_role IN ('ADMIN','MEMBER')),
      enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now());
    INSERT INTO editor.users(id,display_name,system_role) VALUES ('installation-operator','Kurulum yöneticisi','ADMIN');
    CREATE TABLE editor.book_access (
      work_id uuid NOT NULL REFERENCES editor.works, user_id text NOT NULL REFERENCES editor.users,
      role text NOT NULL CHECK(role IN ('EDITOR','READER')), granted_by text NOT NULL REFERENCES editor.users,
      updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(work_id,user_id));
    CREATE TABLE editor.access_keys (
      id uuid PRIMARY KEY, user_id text NOT NULL REFERENCES editor.users,
      label text NOT NULL, token_hash text NOT NULL UNIQUE,
      role text NOT NULL CHECK(role IN ('ADMIN','EDITOR','READER')), work_ids uuid[],
      created_by text NOT NULL REFERENCES editor.users, request_key text NOT NULL, request_hash text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now(), revoked_at timestamptz,
      UNIQUE(created_by,request_key));
    CREATE TABLE editor.access_audit (
      id uuid PRIMARY KEY, actor_id text NOT NULL, action text NOT NULL,
      target_id text NOT NULL, detail jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
    ALTER TABLE editor.idempotency ADD COLUMN required_work_ids uuid[] NOT NULL DEFAULT '{}';
    GRANT SELECT,INSERT,UPDATE ON editor.users,editor.access_keys TO editor_app;
    GRANT SELECT,INSERT,UPDATE,DELETE ON editor.book_access TO editor_app;
    GRANT SELECT,INSERT ON editor.access_audit TO editor_app;
    ''')


def downgrade():
    raise RuntimeError('Restore into a separate installation instead.')
