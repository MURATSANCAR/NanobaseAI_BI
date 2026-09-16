"""Loopback-only session adapter; Timaş Active Directory is the only password verifier.

No API keys or passwords are placed in browser storage. There is no local or demo account:
every session belongs to an enabled directory user who proved their own password.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ORIGIN = os.environ.get('PORTAL_ORIGIN', 'https://portal.nanobase.ai')
DB = os.environ.get('SESSION_DB', '/var/lib/timas-login/sessions.sqlite')
# host, port, netbios, dns_domain, base_dn, bind_user, bind_password. Root-owned, never committed.
AD_FILE = os.environ.get('AD_CONFIG_FILE', '/etc/nanobase/timas-ad.json')
# Sunucuda HTTPS: Secure çerez. Müşteri iç ağında HTTP (COOKIE_SECURE=0): tarayıcı Secure çerezi HTTP'de saklamaz,
# bu yüzden bayrak ve __Secure- öneki birlikte düşer. HttpOnly + SameSite=Strict + Origin denetimi kalır.
SECURE = os.environ.get('COOKIE_SECURE', '1') != '0'
COOKIE = '__Secure-timas_session' if SECURE else 'timas_session'
FLAGS = ('Secure; ' if SECURE else '') + 'HttpOnly; SameSite=Strict'
TTL = 8 * 3600
# Zeki AI chat: internal URL of the chat container, service account token and token secret. Root-owned, never committed.
# {"url": "http://127.0.0.1:4000", "user_id": "...", "token": "...", "sso_secret": "...", "email_domain": "timas.local"}
CHAT_FILE = os.environ.get('CHAT_CONFIG_FILE', '/etc/nanobase/zeki-chat.json')
# sAMAccountName characters only: nothing here can widen the LDAP filter.
ACCOUNT = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
ACTIVE_PERSON = '(&(objectCategory=person)(objectClass=user)(sAMAccountName={})(!(userAccountControl:1.2.840.113556.1.4.803:=2)))'


class DirectoryUnavailable(Exception):
    """The directory could not be asked; the password was not judged."""


def connection():
    db = sqlite3.connect(DB, timeout=5)
    db.execute('CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, username TEXT, expires REAL)')
    if 'display' not in {row[1] for row in db.execute('PRAGMA table_info(sessions)')}:
        db.execute('ALTER TABLE sessions ADD COLUMN display TEXT')
    return db


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def ad_config():
    try:
        with open(AD_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def account_name(username, config):
    """`TIMAS\\ali`, `ali@timas.local` and `ali` name the same account; another domain names none."""
    name = username.strip()
    if '\\' in name:
        domain, name = name.split('\\', 1)
        if domain.lower() != config['netbios'].lower():
            return None
    elif '@' in name:
        name, domain = name.rsplit('@', 1)
        if domain.lower() != config['dns_domain'].lower():
            return None
    return name if ACCOUNT.match(name) else None


def ensure_md4():
    # NTLM needs MD4; OpenSSL 3 dropped it, pycryptodome still has it.
    try:
        hashlib.new('md4', b'')
        return
    except ValueError:
        pass
    try:
        from Crypto.Hash import MD4  # pycryptodome
    except ImportError:
        from Cryptodome.Hash import MD4  # pycryptodomex / Debian-Ubuntu python3-pycryptodome
    builtin = hashlib.new

    class Md4:
        def __init__(self, data=b''):
            self.h = MD4.new(data)

        def update(self, data):
            self.h.update(data)

        def digest(self):
            return self.h.digest()

    hashlib.new = lambda name, data=b'', **kw: Md4(data) if name.lower() == 'md4' else builtin(name, data, **kw)


def ad_verify(username, password):
    """Returns (account, display name) for an enabled directory user whose password is right.

    NTLM, not simple bind: the domain controller has no certificate, and a simple bind would
    carry the password in clear text across the VPN.
    """
    config = ad_config()
    if not config:
        raise DirectoryUnavailable('no directory configuration')
    if not password:
        return None
    account = account_name(username, config)
    if not account:
        return None
    try:
        from ldap3 import NONE, NTLM, SUBTREE, Connection, Server
        from ldap3.core.exceptions import LDAPException
        ensure_md4()
    except ImportError as exc:
        raise DirectoryUnavailable(f'ldap3 missing: {exc}')
    server = Server(config['host'], port=int(config.get('port', 389)), get_info=NONE, connect_timeout=5)
    domain = config['netbios']
    try:
        lookup = Connection(server, user=f"{domain}\\{config['bind_user']}", password=config['bind_password'],
                            authentication=NTLM, receive_timeout=10)
        if not lookup.bind():
            raise DirectoryUnavailable('service account bind refused')
        try:
            lookup.search(config['base_dn'], ACTIVE_PERSON.format(account), SUBTREE,
                          attributes=['sAMAccountName', 'displayName'], size_limit=2)
            if len(lookup.entries) != 1:
                return None
            entry = lookup.entries[0]
            account = str(entry.sAMAccountName.value)
            display = str(entry.displayName.value or account)
        finally:
            lookup.unbind()
        user = Connection(server, user=f'{domain}\\{account}', password=password, authentication=NTLM, receive_timeout=10)
        try:
            return (account, display) if user.bind() else None
        finally:
            user.unbind()
    except LDAPException as exc:
        raise DirectoryUnavailable(type(exc).__name__)


class ChatUnavailable(Exception):
    """The chat server could not be asked or refused the service account."""


def chat_config():
    try:
        with open(CHAT_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def chat_call(config, method, path, query=None, body=None):
    url = config['url'].rstrip('/') + '/api/v1/' + path
    if query:
        url += '?' + urllib.parse.urlencode(query)
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method, headers={
        'X-User-Id': config['user_id'],
        'X-Auth-Token': config['token'],
        'Content-Type': 'application/json',
    })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read() or b'{}')
        except ValueError:
            raise ChatUnavailable(f'HTTP {exc.code}')
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ChatUnavailable(type(exc).__name__)


def chat_login_token(account, display):
    """Makes sure the portal user exists in the chat under the same account name, then returns a login token.

    The chat never sees a password: accounts are created with a random one that nobody knows, and the
    only way in is this token, which the portal issues to a browser that already holds a portal session.
    """
    config = chat_config()
    if not config:
        raise ChatUnavailable('no chat configuration')
    found = chat_call(config, 'GET', 'users.info', {'username': account})
    user = found.get('user') if found.get('success') else None
    if not user:
        created = chat_call(config, 'POST', 'users.create', {
            'username': account,
            'name': display,
            'email': f"{account}@{config.get('email_domain', 'timas.local')}",
            'password': secrets.token_urlsafe(32),
            'verified': True,
            'requirePasswordChange': False,
            'sendWelcomeEmail': False,
            'joinDefaultChannels': True,
        })
        user = created.get('user') if created.get('success') else None
        if not user:
            raise ChatUnavailable(f"user create refused: {created.get('errorType') or created.get('error')}")
    elif not user.get('active', True):
        return None
    elif user.get('name') != display:
        chat_call(config, 'POST', 'users.update', {'userId': user['_id'], 'data': {'name': display}})
    issued = chat_call(config, 'POST', 'users.createToken', {'userId': user['_id'], 'secret': config['sso_secret']})
    token = (issued.get('data') or {}).get('authToken')
    if not token:
        raise ChatUnavailable(f"token refused: {issued.get('errorType') or issued.get('error')}")
    return token


def session(cookie):
    try:
        cookies = SimpleCookie(cookie)
        token = cookies[COOKIE].value
    except (KeyError, ValueError):
        return None
    with connection() as db:
        return db.execute('SELECT username, display FROM sessions WHERE token=? AND expires>?', (digest(token), time.time())).fetchone()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # nginx supplies access logs; never log credentials

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
            # Browser sessions require the same origin on mutations, including nginx subrequests.
            if self.headers.get('X-Original-Method', 'GET') not in ('GET', 'HEAD', 'OPTIONS') and self.headers.get('Origin') != ORIGIN:
                return self.reply(403)
            return self.reply(200 if session(self.headers.get('Cookie', '')) else 401)
        if self.path == '/session':
            row = session(self.headers.get('Cookie', ''))
            if not row:
                return self.reply(401, {'username': None})
            return self.reply(200, {'username': row[0], 'displayName': row[1] or row[0]})
        if self.path == '/chat-sso':
            # Called by the chat page (same origin, credentials included) to sign the portal user in.
            row = session(self.headers.get('Cookie', ''))
            if not row:
                return self.reply(401)
            try:
                token = chat_login_token(row[0], row[1] or row[0])
            except ChatUnavailable as exc:
                print(f'timas-login: chat unavailable ({exc})', file=sys.stderr, flush=True)
                return self.reply(503, {'error': 'Sohbet şu an kullanılamıyor.'})
            if not token:
                return self.reply(403)
            return self.reply(200, {'loginToken': token})
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
            return self.reply(200, cookie=f'{COOKIE}=; Path=/timas/; {FLAGS}; Max-Age=0')
        if self.path != '/login':
            return self.reply(404)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 4096:
                return self.reply(400)
            data = json.loads(self.rfile.read(size))
            username, password = data['username'], data['password']
            if not isinstance(username, str) or not isinstance(password, str):
                return self.reply(400)
        except (ValueError, KeyError, TypeError):
            return self.reply(400)
        try:
            found = ad_verify(username, password)
        except DirectoryUnavailable as exc:
            print(f'timas-login: directory unavailable ({exc})', file=sys.stderr, flush=True)
            return self.reply(503, {'error': 'Şirket dizinine (Active Directory) şu an ulaşılamıyor. Birazdan tekrar deneyin.'})
        if not found:
            return self.reply(401, {'error': 'Kullanıcı adı veya şifre doğru değil.'})
        user, display = found
        token = secrets.token_urlsafe(32)
        with connection() as db:
            db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
            db.execute('INSERT INTO sessions (token, username, expires, display) VALUES (?, ?, ?, ?)', (digest(token), user, time.time() + TTL, display))
        self.reply(200, {'username': user, 'displayName': display}, f'{COOKIE}={token}; Path=/timas/; {FLAGS}; Max-Age={TTL}')


if __name__ == '__main__':
    os.umask(0o077)
    # Sunucuda loopback; müşteri Docker yığınında konteyner ağına açılır (LOGIN_HOST=0.0.0.0, dışa port verilmez).
    ThreadingHTTPServer((os.environ.get('LOGIN_HOST', '127.0.0.1'), 8796), Handler).serve_forever()
