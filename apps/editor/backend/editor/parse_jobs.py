"""Application-side reconciliation of the networkless parser's immutable results."""
import json
import re
import uuid
from psycopg.types.json import Jsonb
from editor.config import connection, RELEASE
from editor.parse_contract import ROOT, QUEUE, validate_source


def reconcile():
    with connection() as db:
        rows = db.execute("SELECT * FROM editor.uploads WHERE status='PARSING' ORDER BY created_at LIMIT 10 FOR UPDATE SKIP LOCKED").fetchall()
        for row in rows:
            path = QUEUE / (str(row['id']) + '.result.json')
            if not path.exists():
                continue
            try:
                result = json.loads(path.read_text())
                if result.get('sha256') != row['expected_sha256']:
                    raise RuntimeError('PARSER_RESULT_SCOPE_MISMATCH')
                if result['status']=='CANCELLED' or (QUEUE/(str(row['id'])+'.cancel.json')).exists():
                    db.execute("UPDATE editor.uploads SET status='CANCELLED',finished_at=now() WHERE id=%s",(row['id'],))
                    continue
                if result['status'] == 'FAILED':
                    raise RuntimeError(result.get('error_code','SOURCE_PARSE_FAILED'))
                if result['status'] != 'COMPLETED':
                    raise RuntimeError('INVALID_PARSER_RESULT')
                manifest = validate_source(ROOT / row['expected_sha256'], row['expected_sha256'], row['expected_bytes'])
            except Exception as exc:
                code = str(exc) if re.fullmatch('[A-Z_]{3,80}',str(exc)) else 'INVALID_PARSER_RESULT'
                db.execute("UPDATE editor.uploads SET status='FAILED',error_code=%s,finished_at=now() WHERE id=%s", (code,row['id']))
                continue
            db.execute('INSERT INTO editor.source_probes(sha256,release,manifest) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                       (row['expected_sha256'], RELEASE, Jsonb(manifest)))
            version = db.execute('''INSERT INTO editor.content_versions(id,edition_id,sha256) VALUES (%s,%s,%s)
                ON CONFLICT(edition_id,sha256) DO UPDATE SET sha256=excluded.sha256 RETURNING id''',
                (uuid.uuid4(), row['edition_id'], row['expected_sha256'])).fetchone()
            db.execute("UPDATE editor.uploads SET status='COMPLETED',content_version_id=%s,finished_at=now() WHERE id=%s", (version['id'], row['id']))
