import os
import hashlib
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DATABASE_NAME = os.environ.get('EDITOR_DB_NAME', 'editor')


def secret(name: str) -> str:
    value = Path('/run/secrets/' + name).read_text().strip()
    if len(value) < 32:
        raise RuntimeError('Installation secret is missing or too short: ' + name)
    return value


def connection(owner=False):
    role = 'editor_owner' if owner else 'editor_app'
    return psycopg.connect(host='postgres', dbname=DATABASE_NAME, user=role,
                           password=secret('db_owner' if owner else 'db_app'),
                           connect_timeout=5, row_factory=dict_row)


RELEASE = os.environ.get('EDITOR_RELEASE', 'unknown')


def code_manifest():
    root=Path(__file__).resolve().parent
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))}
