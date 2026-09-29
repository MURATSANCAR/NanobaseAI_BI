"""Loopback-only session adapter; Timaş Active Directory is the only password verifier.

No API keys or passwords are placed in browser storage. There is no local or demo account:
every session belongs to an enabled directory user who proved their own password.

Giriş olay kaydı (M49): her giriş denemesi, çıkış ve yönetici kapatması `login_events`'e yazılır — hesap adı (yalnız
geçerli biçimdeyse; parola alana yazılmışsa kaydedilmez), sonuç, neden, kaynak adres ve tarayıcı özeti. Parola ve
oturum anahtarı hiçbir yere yazılmaz. Köprü olayları `GET /admin/events` ile çeker; oturum listesi ve kapatma
`/admin/sessions*`. Yönetim uçları yalnız `LOGIN_ADMIN_TOKEN` (en az 24 karakter) başlıkla çalışır; jeton yoksa ya da
istek ters vekilden geldiyse (X-Real-IP taşıyorsa) 404 döner — `/timas/auth/` dışarıya açık olduğu için.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import threading
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
# NanobaseAI Destek (ayrı site, ayrı port): portal oturumu olan kişi orada da otomatik girer.
# Çerez Path=/timas/ olduğu için Destek onu göremez; tarayıcı buraya gelir, 60 sn'lik tek kullanımlık imzalı
# jetonla Destek'e döner. Anahtar Destek sitesiyle ortak (site_config destek_sso_secret). Root-owned, never committed.
DESTEK_URL = os.environ.get('DESTEK_URL', 'https://portal.nanobase.ai:8446').rstrip('/')
DESTEK_SSO_FILE = os.environ.get('DESTEK_SSO_FILE', '/etc/nanobase/destek-sso.key')
DESTEK_TOKEN_TTL = 60
# sAMAccountName characters only: nothing here can widen the LDAP filter.
ACCOUNT = re.compile(r'^[A-Za-z0-9._-]{1,64}$')
# Yönetim uçlarının jetonu (köprüyle aynı). Boşsa /admin/* kapalıdır.
ADMIN_TOKEN = os.environ.get('LOGIN_ADMIN_TOKEN', '')
# Giriş servisindeki olay kopyasının ömrü; uzun süreli kayıt köprünün tablosunda, kendi saklama süresiyle durur.
EVENTS_KEEP_DAYS = float(os.environ.get('LOGIN_EVENTS_KEEP_DAYS', '30'))
ACTIVE_PERSON = '(&(objectCategory=person)(objectClass=user)(sAMAccountName={})(!(userAccountControl:1.2.840.113556.1.4.803:=2)))'


#: Dizinde böyle etkin bir hesap yok (parola sınanmadı). Olay kaydına hesap adı yazılmaz: kişi parolasını kullanıcı
#: adı kutusuna yazmış olabilir.
UNKNOWN_ACCOUNT = object()


class DirectoryUnavailable(Exception):
    """The directory could not be asked; the password was not judged."""


def connection():
    db = sqlite3.connect(DB, timeout=5)
    db.execute('CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, username TEXT, expires REAL)')
    cols = {row[1] for row in db.execute('PRAGMA table_info(sessions)')}
    for name in ('display', 'addr'):
        if name not in cols:
            db.execute(f'ALTER TABLE sessions ADD COLUMN {name} TEXT')
    if 'created' not in cols:
        db.execute('ALTER TABLE sessions ADD COLUMN created REAL')
    db.execute('CREATE TABLE IF NOT EXISTS login_events (id INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL, '
               'username TEXT NOT NULL, ok INTEGER NOT NULL, reason TEXT NOT NULL, addr TEXT, ua_hash TEXT)')
    return db


def safe_account(username, config=None):
    """Olay kaydına yazılacak hesap adı: etki alanı atılmış, küçük harf; geçerli hesap biçiminde değilse (kişi parolayı
    kullanıcı adı kutusuna yazmış olabilir) hiç yazılmaz."""
    name = str(username or '').strip()
    if '\\' in name:
        name = name.split('\\', 1)[1]
    elif '@' in name:
        name = name.rsplit('@', 1)[0]
    return name.lower() if ACCOUNT.match(name) else '(geçersiz biçim)'


def record(db, username, ok, reason, addr=None, ua=None):
    db.execute('INSERT INTO login_events (at, username, ok, reason, addr, ua_hash) VALUES (?, ?, ?, ?, ?, ?)',
               (time.time(), username, 1 if ok else 0, reason, (addr or '')[:64] or None,
                hashlib.sha256(ua.encode()).hexdigest()[:16] if ua else None))
    db.execute('DELETE FROM login_events WHERE at < ?', (time.time() - EVENTS_KEEP_DAYS * 86400,))


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
                return UNKNOWN_ACCOUNT
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
        created = chat_call(config, 'POST', 'users.create', body={
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
        chat_call(config, 'POST', 'users.update', body={'userId': user['_id'], 'data': {'name': display}})
    issued = chat_call(config, 'POST', 'users.createToken', body={'userId': user['_id'], 'secret': config['sso_secret']})
    token = (issued.get('data') or {}).get('authToken')
    if not token:
        raise ChatUnavailable(f"token refused: {issued.get('errorType') or issued.get('error')}")
    return token


# Kampüs'teki sohbet kartı her açık ekranda yarım dakikada bir sorar; sohbete giden istek bu süre içinde bir tanedir.
PRESENCE_TTL = 15
# Sohbetin kendi hesapları (hoş geldin botu, kurulum yöneticisi) kişi sayılmaz.
CHAT_SYSTEM_ACCOUNTS = {'zeki.bot'}
PRESENCE_ORDER = {'online': 0, 'busy': 1, 'away': 2}
_presence = {'at': 0.0, 'value': None}
_presence_lock = threading.Lock()


def chat_presence():
    """Sohbette şu an çevrimdışı olmayan kişiler: {online, people:[{username, name, status}]}.

    Yapılandırma yoksa None (bu kurulumda sohbet yok). Sohbet cevap vermezse ChatUnavailable."""
    config = chat_config()
    if not config:
        return None
    with _presence_lock:
        if _presence['value'] is not None and time.time() - _presence['at'] < PRESENCE_TTL:
            return _presence['value']
        found = chat_call(config, 'GET', 'users.presence')
        if not found.get('success'):
            raise ChatUnavailable(f"presence refused: {found.get('errorType') or found.get('error')}")
        skip = CHAT_SYSTEM_ACCOUNTS | {str(config.get('admin_username') or '').lower()}
        people = [
            {'username': u['username'], 'name': u.get('name') or u['username'], 'status': u.get('status')}
            for u in found.get('users') or []
            if u.get('username') and u.get('_id') != config.get('user_id') and u['username'].lower() not in skip
            and u.get('status') in PRESENCE_ORDER
        ]
        people.sort(key=lambda p: (PRESENCE_ORDER[p['status']], p['name'].casefold()))
        value = {'online': len(people), 'people': people}
        _presence.update(at=time.time(), value=value)
        return value


def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def destek_token(username, display):
    with open(DESTEK_SSO_FILE) as f:
        secret = f.read().strip().encode()
    payload = b64url(json.dumps({'u': username, 'd': display, 'exp': int(time.time()) + DESTEK_TOKEN_TTL,
                                 'n': secrets.token_urlsafe(12)}, separators=(',', ':')).encode())
    return payload + '.' + b64url(hmac.new(secret, payload.encode(), hashlib.sha256).digest())


def safe_next(value):
    # Yalnız Destek içindeki bir yol: açık yönlendirme olmasın.
    return value if value.startswith('/') and not value.startswith('//') and '\\' not in value else '/helpdesk'


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

    def client_addr(self):
        # Ters vekil (nginx) X-Real-IP'yi kendi yazar; yoksa X-Forwarded-For'un ilki, o da yoksa bağlanan adres.
        real = (self.headers.get('X-Real-IP') or '').strip()
        if real:
            return real[:64]
        fwd = (self.headers.get('X-Forwarded-For') or '').split(',')[0].strip()
        return (fwd or self.client_address[0])[:64]

    def admin_ok(self):
        """Yönetim uçları: jeton tanımlı ve eşleşiyor, istek ters vekilden gelmiyor."""
        if len(ADMIN_TOKEN) < 24 or self.headers.get('X-Real-IP'):
            return False
        return hmac.compare_digest(self.headers.get('X-Login-Admin', ''), ADMIN_TOKEN)

    def admin_get(self, path, query):
        if path == '/admin/events':
            try:
                after = int(query.get('after', ['0'])[0])
                limit = max(1, min(int(query.get('limit', ['1000'])[0]), 5000))
            except ValueError:
                return self.reply(400)
            with connection() as db:
                rows = db.execute('SELECT id, at, username, ok, reason, addr, ua_hash FROM login_events WHERE id > ? '
                                  'ORDER BY id LIMIT ?', (after, limit + 1)).fetchall()
                max_id = db.execute('SELECT COALESCE(MAX(id), 0) FROM login_events').fetchone()[0]
            items = [{'id': r[0], 'at': r[1], 'username': r[2], 'ok': bool(r[3]), 'reason': r[4], 'addr': r[5], 'ua': r[6]}
                     for r in rows[:limit]]
            return self.reply(200, {'items': items, 'more': len(rows) > limit, 'maxId': max_id})
        if path == '/admin/sessions':
            with connection() as db:
                rows = db.execute('SELECT token, username, display, created, expires, addr FROM sessions WHERE expires > ? '
                                  'ORDER BY created DESC', (time.time(),)).fetchall()
            # Oturum kimliği: saklanan özetin ilk 16 hanesi (anahtarın kendisi değil; ondan anahtar üretilemez).
            return self.reply(200, {'items': [{'id': r[0][:16], 'username': r[1], 'display': r[2], 'created': r[3],
                                               'expires': r[4], 'addr': r[5]} for r in rows]})
        return self.reply(404)

    def admin_revoke(self):
        try:
            size = int(self.headers.get('Content-Length', '0'))
            data = json.loads(self.rfile.read(size)) if 0 < size <= 4096 else {}
        except (ValueError, TypeError):
            return self.reply(400)
        username = str(data.get('username') or '').strip().lower()
        sid = str(data.get('session') or '').strip().lower()
        if not username and not (len(sid) == 16 and all(c in '0123456789abcdef' for c in sid)):
            return self.reply(400)
        with connection() as db:
            if username:
                rows = db.execute('SELECT token, username FROM sessions WHERE lower(username) = ?', (username,)).fetchall()
            else:
                rows = db.execute('SELECT token, username FROM sessions WHERE substr(token, 1, 16) = ?', (sid,)).fetchall()
            for token, user in rows:
                db.execute('DELETE FROM sessions WHERE token = ?', (token,))
                record(db, (user or '?').lower(), True, 'revoked', 'yonetici:' + str(data.get('actor') or '')[:40])
        return self.reply(200, {'revoked': len(rows)})

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

    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/admin/'):
            if not self.admin_ok():
                return self.reply(404)
            parsed = urllib.parse.urlsplit(self.path)
            return self.admin_get(parsed.path, urllib.parse.parse_qs(parsed.query))
        url = urllib.parse.urlsplit(self.path)
        if url.path == '/destek-sso':
            # Destek'in giriş sayfası tarayıcıyı buraya yollar; portal oturumu varsa imzalı jetonla geri döner,
            # yoksa Destek'in kendi AD giriş formuna (sso=0: döngü olmasın).
            nxt = safe_next(urllib.parse.parse_qs(url.query).get('next', ['/helpdesk'])[0])
            row = session(self.headers.get('Cookie', ''))
            if not row:
                return self.redirect(f"{DESTEK_URL}/login?sso=0&redirect-to={urllib.parse.quote(nxt, safe='/')}")
            try:
                token = destek_token(row[0], row[1] or row[0])
            except OSError as exc:
                print(f'timas-login: destek sso key unavailable ({exc})', file=sys.stderr, flush=True)
                return self.redirect(f"{DESTEK_URL}/login?sso=0&redirect-to={urllib.parse.quote(nxt, safe='/')}")
            return self.redirect(f"{DESTEK_URL}/api/method/nanobase_brand.sso.login?"
                                 + urllib.parse.urlencode({'t': token, 'next': nxt}))
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
        if self.path == '/chat-presence':
            # Kampüs sohbet kartı: kaç kişi çevrimiçi. Yalnız portal oturumu olan görür.
            if not session(self.headers.get('Cookie', '')):
                return self.reply(401)
            try:
                found = chat_presence()
            except ChatUnavailable as exc:
                print(f'timas-login: chat presence unavailable ({exc})', file=sys.stderr, flush=True)
                return self.reply(503, {'error': 'Sohbet şu an cevap vermiyor.'})
            if found is None:
                return self.reply(404, {'configured': False})
            return self.reply(200, found)
        self.reply(404)

    def do_POST(self):
        if self.path == '/admin/sessions/revoke':
            return self.admin_revoke() if self.admin_ok() else self.reply(404)
        if self.headers.get('Origin') != ORIGIN:
            return self.reply(403)
        if self.path == '/logout':
            try:
                token = SimpleCookie(self.headers.get('Cookie', ''))[COOKIE].value
                with connection() as db:
                    row = db.execute('SELECT username FROM sessions WHERE token=?', (digest(token),)).fetchone()
                    db.execute('DELETE FROM sessions WHERE token=?', (digest(token),))
                    if row:
                        record(db, (row[0] or '?').lower(), True, 'logout', self.client_addr(), self.headers.get('User-Agent'))
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
        addr, ua = self.client_addr(), self.headers.get('User-Agent')
        shown = safe_account(username)
        try:
            found = ad_verify(username, password)
        except DirectoryUnavailable as exc:
            print(f'timas-login: directory unavailable ({exc})', file=sys.stderr, flush=True)
            with connection() as db:
                record(db, shown, False, 'directory_down', addr, ua)
            return self.reply(503, {'error': 'Şirket dizinine (Active Directory) şu an ulaşılamıyor. Birazdan tekrar deneyin.'})
        if found is UNKNOWN_ACCOUNT:
            with connection() as db:
                record(db, '(bilinmeyen hesap)', False, 'unknown_account', addr, ua)
            return self.reply(401, {'error': 'Kullanıcı adı veya şifre doğru değil.'})
        if not found:
            config = ad_config() or {}
            reason = 'bad_format' if shown == '(geçersiz biçim)' else (
                'unknown_domain' if config and account_name(username, config) is None else 'bad_password')
            with connection() as db:
                record(db, shown, False, reason, addr, ua)
            return self.reply(401, {'error': 'Kullanıcı adı veya şifre doğru değil.'})
        user, display = found
        token = secrets.token_urlsafe(32)
        with connection() as db:
            db.execute('DELETE FROM sessions WHERE expires<=?', (time.time(),))
            db.execute('INSERT INTO sessions (token, username, expires, display, created, addr) VALUES (?, ?, ?, ?, ?, ?)',
                       (digest(token), user, time.time() + TTL, display, time.time(), addr))
            record(db, user.lower(), True, 'ok', addr, ua)
        self.reply(200, {'username': user, 'displayName': display}, f'{COOKIE}={token}; Path=/timas/; {FLAGS}; Max-Age={TTL}')


if __name__ == '__main__':
    os.umask(0o077)
    # Sunucuda loopback; müşteri Docker yığınında konteyner ağına açılır (LOGIN_HOST=0.0.0.0, dışa port verilmez).
    ThreadingHTTPServer((os.environ.get('LOGIN_HOST', '127.0.0.1'), 8796), Handler).serve_forever()
