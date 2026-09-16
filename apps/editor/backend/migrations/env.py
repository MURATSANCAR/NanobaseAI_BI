from alembic import context
from sqlalchemy import create_engine, URL
from editor.config import secret

engine = create_engine(URL.create('postgresql+psycopg', username='editor_owner',
                       password=secret('db_owner'), host='postgres', database='editor'))
with engine.connect() as connection:
    context.configure(connection=connection, version_table_schema='editor')
    with context.begin_transaction():
        context.run_migrations()
