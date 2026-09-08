"""Loopback-only session adapter; nginx remains the password verifier.

No API keys or passwords are placed in browser storage. Test invitation secrets
are runtime configuration, expire, and never appear in request URLs or logs.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import urllib.request
import urllib.error
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ORIGIN = os.environ.get('PORTAL_ORIGIN', 'https://portal.nanobase.ai')
DB = os.environ.get('SESSION_DB', '/var/lib/timas-login/sessions.sqlite')
INVITE = os.environ.get('INVITE_FILE', '/etc/nanobase/timas-test-invite.json')
VERIFY = os.environ.get('PASSWORD_VERIFY_URL', 'http://127.0.0.1:8797/verify')
COOKIE = '__Secure-timas_session'
TTL = 8 * 3600


def connection():
    db = sqlite3.connect(DB, timeout=5)
    db.execute('CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, username TEXT, expires REAL)')
    return db


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def verify(header):
    if not header.startswith('Basic ') or len(header) > 2048:
        return None
    try:
        decoded = base64.b64decode(header[6:], validate=True).decode('utf8')
        username, password = decoded.split(':', 1)
        if not username or not password:
            return None
        req = urllib.request.Request(VERIFY, headers={'Authorization': header})
        with urllib.request.urlopen(req, timeout=3) as response:
            return username if response.status == 200 else None
    except (ValueError, UnicodeError, urllib.error.URLError):
        return None


def session(cookie):
    try:
        cookies = SimpleCookie(cookie)
        token = cookies[COOKIE].value
    except (KeyError, ValueError):
        return None
    with connection() as db:
        row = db.execute('SELECT username FROM sessions WHERE token=? AND expires>?', (digest(token), time.time())).fetchone()
    return row[0] if row else None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # nginx supplies access logs; never log credentials or invitation headers

    def reply(self, status, data=None, cookie=None):
        raw = json.dumps(data or {}, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/check':
            # Explicit Basic clients remain compatible. Browser sessions also
            # require the same origin on mutations, including nginx subrequests.
            user = verify(self.headers.get('Authorization', ''))
            if not user:
                if self.headers.get('X-Original-Method', 'GET') not in ('GET', 'HEAD', 'OPTIONS') and self.headers.get('Origin') != ORIGIN:
                    return self.reply(403)
                user = session(self.headers.get('Cookie', ''))
            return self.reply(200 if user else 401)
        if self.path == '/session':
            user = session(self.headers.get('Cookie', ''))
            return self.reply(200 if user else 401, {'username': user})
        if self.path == '/prefill':
            try:
                with open(INVITE) as f:
                    config = json.load(f)
                supplied = self.headers.get('X-Test-Invite', '')
                if supplied and hmac.compare_digest(supplied, config['token']) and time.time() < config['expires']:
                    return self.reply(200, {k: config[k] for k in ('username', 'password', 'expires')})
            except (OSError, ValueError, KeyError):
                pass
            return self.reply(403, {'error': 'Test daveti geçersiz veya süresi dolmuş.'})
        self.reply(404)

    def do_POST(self):
        if self.headers.get('Origin') != ORIGIN:
            return self.reply(403)
        if self.path == '/logout':
            try:
                token = SimpleCookie(self.headers.get('Cookie', ''))[COOKIE].value
                with connection() as db:
                    db.execute('DELETE FROM sessions WHERE token=?', (digest(token),))
            except (KeyError, ValueError):
                pass
            return self.reply(200, cookie=f'{COOKIE}=; Path=/timas/; Secure; HttpOnly; SameSite=Strict; Max-Age=0')
        if self.path != '/login':
            return self.reply(404)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                return self.reply(400)
            data = json.loads(self.rfile.read(size))
            username, password = data['username'], data['password']
            if not isinstance(username, str) or not isinstance(password, str) or ':' in username:
                return self.reply(400)
            header = 'Basic ' + base64.b64encode(f'{username}:{password}'.encode()).decode()
        except (ValueError, KeyError, TypeError):
            return self.reply(400)
        user = verify(header)
        if not user:
            return self.reply(401, {'error': 'Kullanıcı adı veya şifre doğru değil.'})
        token = secrets.token_urlsafe(32)
        with connection() as db:
            db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
            db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (digest(token), user, time.time() + TTL))
        self.reply(200, {'username': user}, f'{COOKIE}={token}; Path=/timas/; Secure; HttpOnly; SameSite=Strict; Max-Age={TTL}')


if __name__ == '__main__':
    os.umask(0o077)
    ThreadingHTTPServer(('127.0.0.1', 8796), Handler).serve_forever()
