"""Resolve the nearest completed page in an immutable, same-content lineage.

This selects measurement/proposal provenance only. It does not certify source
text, reuse editorial acceptance, or bypass the consumer's current source gates.
"""
import re
import uuid

from editor.config import connection

REQUIRED_KINDS = ('page_readings', 'layout_regions', 'visual_observations', 'page_claims', 'page_checks')
MAX_DEPTH = 64


def resolve_page_parent(parent_generation, record_key, content_version_id):
    if not isinstance(record_key, str) or not re.fullmatch(r'[0-9]{4,}', record_key) or int(record_key) < 1:
        raise ValueError('INVALID_PAGE_RECORD_KEY')
    content_version = uuid.UUID(str(content_version_id))
    if parent_generation is None:
        return None
    current = uuid.UUID(str(parent_generation))
    visited = set()
    # One consistent, read-only snapshot; a concurrent page commit can be picked
    # up by the next caller, never pieced together from different snapshots.
    with connection() as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        for _ in range(MAX_DEPTH):
            if current in visited:
                raise RuntimeError('PAGE_REUSE_LINEAGE_CYCLE')
            visited.add(current)
            generation = db.execute('SELECT content_version_id,manifest FROM editor.generations WHERE id=%s', (current,)).fetchone()
            if generation is None:
                raise RuntimeError('PAGE_REUSE_PARENT_MISSING')
            if generation['content_version_id'] != content_version:
                raise RuntimeError('PAGE_REUSE_CONTENT_VERSION_MISMATCH')
            records = db.execute('SELECT kind,data FROM editor.records WHERE generation_id=%s AND record_key=%s AND kind=ANY(%s)',
                                 (current, record_key, list(REQUIRED_KINDS))).fetchall()
            if any(row['data'].get('pdf_page') != int(record_key) for row in records):
                raise RuntimeError('PAGE_REUSE_RECORD_SCOPE_MISMATCH')
            if len(records) == len(REQUIRED_KINDS) and {row['kind'] for row in records} == set(REQUIRED_KINDS):
                return str(current)
            previous = generation['manifest'].get('reuse_measurements_from')
            if previous is None:
                return None
            try:
                current = uuid.UUID(str(previous))
            except (TypeError, ValueError, AttributeError) as exc:
                raise RuntimeError('PAGE_REUSE_INVALID_PARENT_ID') from exc
        raise RuntimeError('PAGE_REUSE_DEPTH_EXCEEDED')
