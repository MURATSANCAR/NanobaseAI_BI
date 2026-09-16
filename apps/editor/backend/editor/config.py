import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


def secret(name: str) -> str:
    value = Path('/run/secrets/' + name).read_text().strip()
    if len(value) < 32:
        raise RuntimeError('Installation secret is missing or too short: ' + name)
    return value


def connection(owner=False):
    role = 'editor_owner' if owner else 'editor_app'
    return psycopg.connect(host='postgres', dbname='editor', user=role,
                           password=secret('db_owner' if owner else 'db_app'),
                           connect_timeout=5, row_factory=dict_row)


RELEASE = os.environ.get('EDITOR_RELEASE', 'unknown')
