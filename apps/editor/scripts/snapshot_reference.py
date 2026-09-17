"""Content fingerprints for a quiescent real installation; never log source text."""
import hashlib
import json
import subprocess


def book_reference(config, tables=None):
    compose = ['docker', 'compose']
    allowed = ('works', 'editions', 'content_versions', 'generations', 'jobs',
              'records', 'reviews', 'idempotency', 'uploads', 'outbox',
              'users', 'book_access', 'access_keys', 'access_audit')
    tables = allowed if tables is None else tuple(tables)
    if not tables or any(t not in allowed for t in tables):
        raise ValueError('Unexpected book reference table')
    database = {}
    for table in tables:
        # PostgreSQL owns the canonical JSON representation on both installations.
        query = f"COPY (SELECT row_to_json(t)::text FROM editor.{table} t ORDER BY row_to_json(t)::text COLLATE \"C\") TO STDOUT"
        result = subprocess.check_output(compose + ['exec', '-T', 'postgres',
            'psql', '-U', 'postgres', '-d', 'editor', '-Atc', query])
        database[table] = {'sha256': hashlib.sha256(result).hexdigest(),
                           'rows': result.count(b'\n')}
    code = '''import hashlib,json,pathlib
root=pathlib.Path('/data/artifacts'); result={}
for path in sorted(root.rglob('*')):
 if path.is_file():
  with path.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
  result[str(path.relative_to(root))]={'sha256':digest,'bytes':path.stat().st_size}
print(json.dumps(result,sort_keys=True))
'''
    artifacts = json.loads(subprocess.check_output([
        'docker', 'run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '-v', config['volumes']['artifacts']['name'] + ':/data/artifacts:ro',
        config['services']['api']['image'], 'python', '-c', code]))
    return {'database': database, 'artifacts': artifacts}
