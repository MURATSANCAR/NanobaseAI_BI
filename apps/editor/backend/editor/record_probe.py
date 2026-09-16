"""Operator-only import of a completed real source probe, never an accepted book generation."""
import hashlib
import json
from pathlib import Path
import sys
from psycopg.types.json import Jsonb
from editor.config import connection, RELEASE

path = Path(sys.argv[1]).resolve()
if not path.is_relative_to('/data/artifacts'):
    raise SystemExit('Probe must be in artifact storage')
manifest = json.loads(path.read_text())
with (path.parent/'original.pdf').open('rb') as stream:
    assert hashlib.file_digest(stream,'sha256').hexdigest() == manifest['sha256']
assert manifest['source_accounting_complete']
assert len(manifest['pages']) == manifest['pdf_pages']
with connection() as db:
    db.execute('INSERT INTO editor.source_probes(sha256,release,manifest) VALUES (%s,%s,%s) ON CONFLICT(sha256) DO NOTHING',
               (manifest['sha256'], RELEASE, Jsonb(manifest)))
print('Source probe recorded; semantic analysis remains NOT_ANALYZED.')
