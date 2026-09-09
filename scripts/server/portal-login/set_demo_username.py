"""Rename the configured demo account without changing its password or access policy."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import tempfile


def replace_file(path, text):
    stat = path.stat()
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(name, stat.st_mode & 0o777)
        os.chown(name, stat.st_uid, stat.st_gid)
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def rename(invite, passwords, sessions, username='Timas'):
    if not username or any(c in username for c in ':\r\n'):
        raise ValueError('Invalid username')
    config = json.loads(invite.read_text())
    old = config['username']
    lines = passwords.read_text().splitlines()
    matches = [line for line in lines if line.split(':', 1)[0] == old]
    if len(matches) != 1:
        raise ValueError('Configured account must exist exactly once')
    if old != username and any(line.split(':', 1)[0] == username for line in lines):
        raise ValueError('Target username already exists; no changes made')
    updated = [username + ':' + line.split(':', 1)[1] if line.split(':', 1)[0] == old else line for line in lines]
    config['username'] = username
    replace_file(passwords, '\n'.join(updated) + '\n')
    replace_file(invite, json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    if sessions.exists():
        with sqlite3.connect(sessions) as db:
            db.execute('UPDATE sessions SET username=? WHERE username=?', (username, old))
    return {'username': username, 'passwordUnchanged': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--username', default=os.environ.get('TIMAS_USER', 'Timas'))
    parser.add_argument('--invite', type=Path, default=Path('/etc/nanobase/timas-test-invite.json'))
    parser.add_argument('--passwords', type=Path, default=Path('/etc/nginx/htpasswd-timas'))
    parser.add_argument('--sessions', type=Path, default=Path('/var/lib/timas-login/sessions.sqlite'))
    args = parser.parse_args()
    print(json.dumps(rename(args.invite, args.passwords, args.sessions, args.username)))
