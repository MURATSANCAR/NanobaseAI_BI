"""Book scope, immutable evidence and fenced writes. No book-specific answers."""
import hashlib
import json
import uuid
from pathlib import Path
from psycopg.types.json import Jsonb
from editor.config import connection

ROOT = Path('/data/artifacts')


def identifier(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'editor:' + ':'.join(map(str, parts))))


def sha(value):
    return hashlib.sha256(value).hexdigest()


def get_records(generation, kind):
    with connection() as db:
        return db.execute('SELECT id,record_key,data FROM editor.records WHERE generation_id=%s AND kind=%s ORDER BY record_key', (generation,kind)).fetchall()


def save_record(db, generation, kind, key, data, index=False):
    rid = identifier(generation,kind,key)
    db.execute('INSERT INTO editor.records(id,generation_id,kind,record_key,data) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', (rid,generation,kind,key,Jsonb(data)))
    if index:
        db.execute('INSERT INTO editor.outbox(id,generation_id) VALUES (%s,%s) ON CONFLICT DO NOTHING', (rid,generation))
    return rid


def fence(db, job):
    row = db.execute("SELECT cancellation_requested FROM editor.jobs WHERE id=%s AND fencing_token=%s AND owner_id=%s AND status='RUNNING' AND lease_until>now() FOR UPDATE", (job['id'],job['fencing_token'],job['owner_id'])).fetchone()
    if not row:
        raise RuntimeError('LEASE_LOST')
    if row['cancellation_requested']:
        raise RuntimeError('CANCELLED')


def source_for(generation):
    with connection() as db:
        return db.execute('''SELECT cv.sha256,cv.id AS content_version_id,e.work_id,s.manifest
          FROM editor.generations g JOIN editor.content_versions cv ON cv.id=g.content_version_id
          JOIN editor.editions e ON e.id=cv.edition_id JOIN editor.source_probes s ON s.sha256=cv.sha256
          WHERE g.id=%s''',(generation,)).fetchone()
