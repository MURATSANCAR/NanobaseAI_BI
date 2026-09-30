"""Remote browser acceptance: real UI/result/export + independently computed Logo reference."""
import csv
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import time
from live import environment, connect, query, cases, compare, code_manifest

if sys.platform != 'linux':
    raise SystemExit('Test server only')
os.umask(0o077)
out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
login = environment('timas-login')
session = sqlite3.connect(login.get('SESSION_DB', '/var/lib/timas-login/sessions.sqlite'))
token = secrets.token_urlsafe(32); digest = hashlib.sha256(token.encode()).hexdigest()
session.execute('INSERT INTO sessions(token,username,expires) VALUES(?,?,?)', (digest, 'timasai', time.time()+900)); session.commit()
before = code_manifest(); report = {'status': 'UNVERIFIED', 'sourceWrites': 0}
try:
    case = next(c for c in cases() if c['id'] == 'FC18')
    conn = connect('/data/nanobaseai/bi/secrets/logo-mssql-connection.json')
    try: reference = query(conn, case['referenceSql'])
    finally: conn.close()
    subprocess.run(['node', str(Path(__file__).with_suffix('.cjs'))], env={**os.environ, 'FINANCE_UI_TOKEN': token, 'FINANCE_UI_OUT': str(out)}, timeout=360, check=True)
    answer = json.loads((out/'answer.json').read_text()); whole = json.loads((out/'full.json').read_text())
    errors = compare(case, answer, whole, reference)
    with (out/'result.csv').open(encoding='utf-8-sig', newline='') as stream: exported = list(csv.reader(stream, delimiter=';'))
    columns = whole['columns']
    if len(exported) != len(reference)+1: errors.append('CSV row count mismatch')
    expected = []
    for row in whole['records']:
        cells = []
        for col in columns:
            value = row[col['name']]
            text = '' if value is None else str(value)
            if isinstance(value, str) and text.lstrip()[:1] in ('=', '+', '@', '-'): text = "'"+text
            cells.append(text)
        expected.append(cells)
    # JS renders integral floats without .0; compare numeric cells numerically, text exactly.
    for actual, wanted, row in zip(exported[1:], expected, whole['records']):
        for idx, col in enumerate(columns):
            value = row[col['name']]
            if isinstance(value, (int, float)):
                if float(actual[idx]) != value: errors.append('CSV numeric value mismatch')
            elif actual[idx] != wanted[idx]: errors.append('CSV text value mismatch')
    if before != code_manifest(): errors.append('Server code changed during acceptance')
    report.update(status='FAIL' if errors else 'PASS', errors=errors[:15], rows=len(reference), browser=json.loads((out/'browser.json').read_text()))
except Exception as exc:
    report['error'] = str(exc)
finally:
    report['sessionsDeleted'] = session.execute('DELETE FROM sessions WHERE token=?', (digest,)).rowcount
    session.commit(); session.close()
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False))
sys.exit(0 if report['status'] == 'PASS' else 1)
