"""Run once before API/worker. Application credentials cannot perform DDL."""
from alembic import command
from alembic.config import Config
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg
from psycopg.conninfo import make_conninfo

from editor.config import connection, secret, RELEASE


def main():
    command.upgrade(Config('/app/alembic.ini'), 'head')
    dsn = make_conninfo(host='postgres', dbname='editor', user='editor_owner',
                       password=secret('db_owner'), options='-c search_path=checkpoints')
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.setup()
    with connection(owner=True) as db:
        db.execute('GRANT USAGE ON SCHEMA editor TO editor_app')
        db.execute('GRANT SELECT ON editor.deployments, editor.alembic_version TO editor_app')
        db.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON editor.worker_heartbeats TO editor_app')
        db.execute('GRANT SELECT, INSERT ON editor.source_probes TO editor_app')
        # pg_restore deliberately omits ACLs; reapply book grants even when the
        # restored Alembic revision is already current and no migration runs.
        db.execute('''GRANT SELECT, INSERT, UPDATE ON editor.works, editor.editions,
            editor.content_versions, editor.generations, editor.jobs, editor.records,
            editor.outbox, editor.reviews, editor.idempotency, editor.uploads TO editor_app''')
        db.execute('GRANT USAGE ON SCHEMA checkpoints TO editor_app')
        db.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA checkpoints TO editor_app')
        db.execute('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA checkpoints TO editor_app')
        db.execute('INSERT INTO editor.deployments(release) VALUES (%s) ON CONFLICT (release) DO NOTHING', (RELEASE,))
    print('Migrations and PostgreSQL checkpointer ready: ' + RELEASE)


if __name__ == '__main__':
    main()
