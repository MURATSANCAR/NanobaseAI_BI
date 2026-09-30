import http.client
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('login', pathlib.Path(__file__).with_name('server.py'))
login = importlib.util.module_from_spec(spec)
spec.loader.exec_module(login)


class Sessions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        login.DB = self.tmp.name + '/sessions.db'
        self.server = login.ThreadingHTTPServer(('127.0.0.1', 0), login.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def request(self, path, method='GET', data=None, headers=None):
        conn = http.client.HTTPConnection(*self.server.server_address)
        conn.request(method, path, json.dumps(data) if data is not None else None, headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), json.loads(response.read())
        conn.close()
        return result

    def login(self, found=('muratsancar', 'Murat Sancar'), username='TIMAS\\muratsancar'):
        with patch.object(login, 'ad_verify', return_value=found):
            return self.request('/login', 'POST', {'username': username, 'password': 'secret'}, {'Origin': login.ORIGIN})

    def test_login_logout_and_cookie_protection(self):
        status, headers, data = self.login()
        self.assertEqual((status, data['username'], data['displayName']), (200, 'muratsancar', 'Murat Sancar'))
        cookie = headers['Set-Cookie']
        for flag in ('Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/timas/'):
            self.assertIn(flag, cookie)
        headers = {'Cookie': cookie.split(';')[0], 'Origin': login.ORIGIN}
        status, _, data = self.request('/session', headers=headers)
        self.assertEqual((status, data['username'], data['displayName']), (200, 'muratsancar', 'Murat Sancar'))
        self.assertEqual(self.request('/check', headers=headers)[0], 200)
        self.assertEqual(self.request('/check', headers={**headers, 'Origin': 'https://evil.invalid', 'X-Original-Method': 'POST'})[0], 403)
        self.assertEqual(self.request('/logout', 'POST', headers=headers)[0], 200)
        self.assertEqual(self.request('/session', headers=headers)[0], 401)

    def raw(self, path, headers=None):
        conn = http.client.HTTPConnection(*self.server.server_address)
        conn.request('GET', path, None, headers or {})
        response = conn.getresponse()
        response.read()
        conn.close()
        return response.status, dict(response.getheaders())

    def test_destek_sso_signs_the_portal_user_into_destek(self):
        import base64, hashlib, hmac, urllib.parse
        key = pathlib.Path(self.tmp.name) / 'destek-sso.key'
        key.write_text('gizli-anahtar\n')
        login.DESTEK_SSO_FILE = str(key)
        # Portal oturumu yok: Destek'in kendi AD girişine, döngüsüz (sso=0).
        status, headers = self.raw('/destek-sso?next=/helpdesk/tickets')
        self.assertEqual(status, 302)
        self.assertEqual(headers['Location'], login.DESTEK_URL + '/login?sso=0&redirect-to=/helpdesk/tickets')
        cookie = self.login()[1]['Set-Cookie'].split(';')[0]
        status, headers = self.raw('/destek-sso?next=/helpdesk/tickets', {'Cookie': cookie})
        self.assertEqual(status, 302)
        loc = urllib.parse.urlsplit(headers['Location'])
        self.assertEqual(f'{loc.scheme}://{loc.netloc}{loc.path}', login.DESTEK_URL + '/api/method/nanobase_brand.sso.login')
        q = urllib.parse.parse_qs(loc.query)
        self.assertEqual(q['next'], ['/helpdesk/tickets'])
        payload, sig = q['t'][0].split('.')
        good = base64.urlsafe_b64encode(hmac.new(b'gizli-anahtar', payload.encode(), hashlib.sha256).digest()).rstrip(b'=').decode()
        self.assertEqual(sig, good)
        data = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        self.assertEqual((data['u'], data['d']), ('muratsancar', 'Murat Sancar'))
        self.assertTrue(0 < data['exp'] - time.time() <= 60)
        # Açık yönlendirme yok: dış adres ve // Destek ana sayfasına döner.
        for bad in ('https://evil.invalid/x', '//evil.invalid', '/\\evil'):
            _, headers = self.raw('/destek-sso?' + urllib.parse.urlencode({'next': bad}), {'Cookie': cookie})
            self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(headers['Location']).query)['next'], ['/helpdesk'])

    def test_invalid_credentials_no_session(self):
        status, headers, _ = self.login(found=None, username='bad')
        self.assertEqual(status, 401)
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual(self.request('/check')[0], 401)

    def test_basic_header_is_not_a_session(self):
        # The demo account is gone: a Basic header, however well formed, opens nothing.
        self.assertEqual(self.request('/check', headers={'Authorization': 'Basic VGltYXM6cGFzcw=='})[0], 401)

    def test_demo_prefill_is_gone(self):
        self.assertEqual(self.request('/prefill')[0], 404)

    def test_cross_site_login_denied(self):
        self.assertEqual(self.request('/login', 'POST', {}, {'Origin': 'https://evil.invalid'})[0], 403)

    def test_unreachable_directory_is_not_a_wrong_password(self):
        with patch.object(login, 'ad_verify', side_effect=login.DirectoryUnavailable('LDAPSocketOpenError')):
            status, headers, data = self.request('/login', 'POST', {'username': 'ali', 'password': 'secret'}, {'Origin': login.ORIGIN})
        self.assertEqual(status, 503)
        self.assertNotIn('Set-Cookie', headers)
        self.assertIn('Active Directory', data['error'])

    def test_missing_directory_configuration_is_unavailable(self):
        with patch.object(login, 'ad_config', return_value=None):
            with self.assertRaises(login.DirectoryUnavailable):
                login.ad_verify('ali', 'secret')

    def test_account_name_accepts_only_this_domain_and_plain_names(self):
        config = {'netbios': 'TIMAS', 'dns_domain': 'timas.local'}
        for given, expected in (('TIMAS\\ali', 'ali'), ('timas\\ali', 'ali'), ('ali@timas.local', 'ali'), (' ali ', 'ali'),
                                ('OTHER\\ali', None), ('ali@evil.invalid', None), ('a*)(uid=*', None), ('', None)):
            self.assertEqual(login.account_name(given, config), expected, given)

    def test_empty_password_never_reaches_directory(self):
        with patch.object(login, 'ad_config', return_value={'netbios': 'TIMAS', 'dns_domain': 'timas.local'}):
            self.assertIsNone(login.ad_verify('ali', ''))

    def test_expired_session_denied(self):
        with login.connection() as db:
            db.execute('INSERT INTO sessions (token, username, expires) VALUES (?, ?, ?)', (login.digest('expired'), 'test', time.time() - 1))
        self.assertEqual(self.request('/session', headers={'Cookie': login.COOKIE + '=expired'})[0], 401)

    def test_sessions_from_before_display_names_still_work(self):
        db = sqlite3.connect(login.DB)
        db.execute('CREATE TABLE sessions (token TEXT PRIMARY KEY, username TEXT, expires REAL)')
        db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (login.digest('old'), 'ali', time.time() + 100))
        db.commit()
        db.close()
        status, _, data = self.request('/session', headers={'Cookie': login.COOKIE + '=old'})
        self.assertEqual((status, data['displayName']), (200, 'ali'))


    # ------------------------------------------------------------------ M49 giriş olay kaydı ve yönetim uçları

    def events(self):
        with login.connection() as db:
            return db.execute('SELECT username, ok, reason, addr FROM login_events ORDER BY id').fetchall()

    def test_login_attempts_are_recorded_without_password(self):
        self.login()
        self.login(found=None, username='TIMAS\\muratsancar')
        with patch.object(login, 'ad_verify', return_value=login.UNKNOWN_ACCOUNT):
            self.request('/login', 'POST', {'username': 'Parola123', 'password': 'x'}, {'Origin': login.ORIGIN})
        self.login(found=None, username='bu bir parola!')
        rows = self.events()
        self.assertEqual([(r[0], r[1], r[2]) for r in rows], [
            ('muratsancar', 1, 'ok'), ('muratsancar', 0, 'bad_password'),
            ('(bilinmeyen hesap)', 0, 'unknown_account'), ('(geçersiz biçim)', 0, 'bad_format')])
        with login.connection() as db:
            dump = ' '.join(str(x) for row in db.execute('SELECT * FROM login_events') for x in row)
        self.assertNotIn('secret', dump)
        self.assertNotIn('parola123', dump.lower())

    def test_directory_down_is_recorded(self):
        with patch.object(login, 'ad_verify', side_effect=login.DirectoryUnavailable('x')):
            self.request('/login', 'POST', {'username': 'ali', 'password': 'secret'}, {'Origin': login.ORIGIN})
        self.assertEqual([(r[0], r[2]) for r in self.events()], [('ali', 'directory_down')])

    def test_real_ip_from_proxy_is_the_address(self):
        with patch.object(login, 'ad_verify', return_value=('ali', 'Ali')):
            self.request('/login', 'POST', {'username': 'ali', 'password': 'secret'},
                         {'Origin': login.ORIGIN, 'X-Real-IP': '10.1.2.3'})
        self.assertEqual(self.events()[-1][3], '10.1.2.3')

    def test_admin_endpoints_need_token_and_are_closed_through_proxy(self):
        token = 'k' * 32
        with patch.object(login, 'ADMIN_TOKEN', ''):
            self.assertEqual(self.request('/admin/events', headers={'X-Login-Admin': ''})[0], 404)
        with patch.object(login, 'ADMIN_TOKEN', token):
            self.assertEqual(self.request('/admin/events', headers={'X-Login-Admin': 'yanlis'})[0], 404)
            self.assertEqual(self.request('/admin/events', headers={'X-Login-Admin': token, 'X-Real-IP': '1.2.3.4'})[0], 404)
            self.assertEqual(self.request('/admin/sessions/revoke', 'POST', {'username': 'ali'},
                                          {'X-Login-Admin': token, 'X-Real-IP': '1.2.3.4'})[0], 404)

    def test_admin_events_sessions_and_revoke(self):
        token = 'k' * 32
        status, headers, _ = self.login()
        cookie = {'Cookie': headers['Set-Cookie'].split(';')[0]}
        with patch.object(login, 'ADMIN_TOKEN', token):
            h = {'X-Login-Admin': token}
            status, _, data = self.request('/admin/events?after=0', headers=h)
            self.assertEqual((status, len(data['items']), data['more']), (200, 1, False))
            self.assertEqual(data['items'][0]['username'], 'muratsancar')
            status, _, data = self.request('/admin/sessions', headers=h)
            self.assertEqual(status, 200)
            self.assertEqual([s['username'] for s in data['items']], ['muratsancar'])
            sid = data['items'][0]['id']
            self.assertEqual(len(sid), 16)
            self.assertNotIn(cookie['Cookie'].split('=', 1)[1], json.dumps(data))
            self.assertEqual(self.request('/admin/sessions/revoke', 'POST', {'session': sid, 'actor': 'zekiai'}, h)[2], {'revoked': 1})
            self.assertEqual(self.request('/session', headers=cookie)[0], 401)
            self.assertEqual(self.events()[-1][2], 'revoked')
            self.assertEqual(self.request('/admin/sessions/revoke', 'POST', {'session': 'zz'}, h)[0], 400)

    def test_logout_is_recorded(self):
        _, headers, _ = self.login()
        self.request('/logout', 'POST', headers={'Cookie': headers['Set-Cookie'].split(';')[0], 'Origin': login.ORIGIN})
        self.assertEqual([r[2] for r in self.events()], ['ok', 'logout'])

    def test_chat_presence_counts_people_not_system_accounts(self):
        login._presence.update(at=0.0, value=None)
        config = {'url': 'http://chat', 'user_id': 'svc', 'token': 't', 'admin_username': 'zekiadmin'}
        users = [
            {'_id': 'svc', 'username': 'zekiservis', 'status': 'online'},
            {'_id': 'zeki.bot', 'username': 'zeki.bot', 'status': 'online'},
            {'_id': 'rocket.cat', 'username': 'zeki.bot', 'status': 'online'},
            {'_id': 'adm', 'username': 'zekiadmin', 'status': 'online'},
            {'_id': 'a', 'username': 'zeynep', 'name': 'Zeynep Ak', 'status': 'away'},
            {'_id': 'b', 'username': 'ali', 'name': 'Ali Can', 'status': 'online'},
            {'_id': 'c', 'username': 'can', 'name': 'Can Er', 'status': 'offline'},
        ]
        self.assertEqual(self.request('/chat-presence')[0], 401)
        cookie = {'Cookie': self.login()[1]['Set-Cookie'].split(';')[0]}
        with patch.object(login, 'chat_config', return_value=None):
            self.assertEqual(self.request('/chat-presence', headers=cookie)[:3:2], (404, {'configured': False}))
        with patch.object(login, 'chat_config', return_value=config), \
                patch.object(login, 'chat_call', return_value={'success': True, 'users': users}) as call:
            status, _, data = self.request('/chat-presence', headers=cookie)
            self.assertEqual(status, 200)
            self.assertEqual(data['online'], 2)
            self.assertEqual([p['username'] for p in data['people']], ['ali', 'zeynep'])
            self.request('/chat-presence', headers=cookie)
            self.assertEqual(call.call_count, 1)
        login._presence.update(at=0.0, value=None)
        with patch.object(login, 'chat_config', return_value=config), \
                patch.object(login, 'chat_call', side_effect=login.ChatUnavailable('URLError')):
            self.assertEqual(self.request('/chat-presence', headers=cookie)[0], 503)

    def test_chat_sso_never_signs_in_as_the_bot(self):
        config = {'url': 'http://chat', 'user_id': 'svc', 'token': 't', 'sso_secret': 's'}
        bot = {'success': True, 'user': {'_id': 'rocket.cat', 'username': 'zeki.bot', 'type': 'bot', 'active': True}}
        with patch.object(login, 'chat_config', return_value=config), patch.object(login, 'chat_call', return_value=bot) as call:
            self.assertIsNone(login.chat_login_token('zeki.bot', 'Zeki'))
            self.assertEqual(call.call_count, 1)


class FakeChat:
    """Sohbet sunucusunun servis hesabıyla çağrılan REST uçlarının sahtesi: kullanıcılar, roller, dil."""

    def __init__(self, users=None):
        self.users = users or {}
        self.calls = []

    def __call__(self, config, method, path, query=None, body=None):
        self.calls.append((method, path, query, body))
        if path == 'users.info':
            u = self.users.get(query['username'])
            return {'success': True, 'user': json.loads(json.dumps(u))} if u else {'success': False, 'error': 'User not found.'}
        if path == 'users.create':
            u = {'_id': 'id-' + body['username'], 'username': body['username'], 'name': body['name'], 'active': True,
                 'roles': ['user']}
            self.users[body['username']] = u
            return {'success': True, 'user': json.loads(json.dumps(u))}
        by_id = {u['_id']: u for u in self.users.values()}
        if path == 'users.update':
            by_id[body['userId']].update(body['data'])
            return {'success': True}
        if path == 'users.setPreferences':
            by_id[body['userId']]['language'] = body['data']['language']
            return {'success': True}
        if path == 'roles.addUserToRole':
            self.users[body['username']]['roles'].append(body['roleId'])
            return {'success': True}
        if path == 'roles.removeUserFromRole':
            self.users[body['username']]['roles'].remove(body['roleId'])
            return {'success': True}
        if path == 'users.createToken':
            return {'success': True, 'data': {'authToken': 'tok-' + body['userId']}}
        raise AssertionError(path)

    def writes(self):
        return [(p, b) for m, p, _, b in self.calls if m == 'POST' and p != 'users.createToken']


class ChatSso(unittest.TestCase):
    """/chat-sso: portalda oturumu olan herkes sohbete girer; yönetici rolü portal yetkisini izler, dil bir kez çekilir."""

    request = Sessions.request
    login = Sessions.login

    def setUp(self):
        Sessions.setUp(self)
        conf = pathlib.Path(self.tmp.name) / 'chat.json'
        conf.write_text(json.dumps({'url': 'http://chat.invalid', 'user_id': 'svc', 'token': 't', 'sso_secret': 's'}))
        self.patches = [patch.object(login, 'CHAT_FILE', str(conf)), patch.object(login, 'chat_call', FakeChat()),
                        patch.object(login, 'portal_can_manage_chat', self.can)]
        for p in self.patches:
            p.start()
        self.chat = login.chat_call
        self.perm = False
        self.asked = []

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        Sessions.tearDown(self)

    def can(self, token):
        self.asked.append(token)
        return self.perm

    def sso(self, found=('muratsancar', 'Murat Sancar')):
        cookie = self.login(found=found, username=found[0])[1]['Set-Cookie'].split(';')[0]
        return self.request('/chat-sso', headers={'Cookie': cookie}), cookie.split('=', 1)[1]

    def test_no_portal_session_no_token(self):
        self.assertEqual(self.request('/chat-sso')[0], 401)
        self.assertEqual(self.chat.calls, [])

    def test_first_visit_opens_the_account_in_turkish_without_admin(self):
        (status, _, data), token = self.sso(('ayse', 'Ayşe Yılmaz'))
        self.assertEqual((status, data), (200, {'loginToken': 'tok-id-ayse'}))
        u = self.chat.users['ayse']
        self.assertEqual((u['name'], u['language'], u['roles']), ('Ayşe Yılmaz', 'tr', ['user']))
        self.assertEqual(self.asked, [token])                      # yetki kişinin kendi oturumuyla soruldu
        create = [b for p, b in self.chat.writes() if p == 'users.create'][0]
        self.assertTrue(create['joinDefaultChannels'] and create['verified'])
        self.assertEqual(create['username'], 'ayse')
        # İkinci giriş: dil yeniden yazılmaz, rol değişmez.
        self.chat.calls.clear()
        self.sso(('ayse', 'Ayşe Yılmaz'))
        self.assertEqual(self.chat.writes(), [])

    def test_admin_role_follows_the_portal_permission(self):
        self.perm = True
        self.sso()
        self.assertIn('admin', self.chat.users['muratsancar']['roles'])
        self.perm = False
        self.sso()
        self.assertNotIn('admin', self.chat.users['muratsancar']['roles'])
        self.perm = True
        self.sso()
        self.assertIn('admin', self.chat.users['muratsancar']['roles'])

    def test_role_given_by_hand_in_the_chat_is_kept(self):
        self.chat.users['ali'] = {'_id': 'id-ali', 'username': 'ali', 'name': 'Ali', 'active': True,
                                  'roles': ['user', 'admin'], 'language': 'tr'}
        self.perm = True
        self.sso(('ali', 'Ali'))
        self.perm = False
        self.sso(('ali', 'Ali'))
        self.assertIn('admin', self.chat.users['ali']['roles'])   # bu servis vermedi, geri almaz
        self.assertEqual(self.chat.writes(), [])

    def test_unknown_permission_changes_no_role(self):
        self.perm = True
        self.sso()
        self.perm = None                                            # köprü cevap vermedi
        self.sso()
        self.assertIn('admin', self.chat.users['muratsancar']['roles'])

    def test_language_only_pulled_from_empty_or_english_once(self):
        self.chat.users['veli'] = {'_id': 'id-veli', 'username': 'veli', 'name': 'Veli', 'active': True,
                                   'roles': ['user'], 'language': 'de'}
        self.chat.users['can'] = {'_id': 'id-can', 'username': 'can', 'name': 'Can', 'active': True,
                                  'roles': ['user'], 'language': 'en'}
        self.sso(('veli', 'Veli'))
        self.sso(('can', 'Can'))
        self.assertEqual((self.chat.users['veli']['language'], self.chat.users['can']['language']), ('de', 'tr'))
        self.chat.users['can']['language'] = 'en'                   # kişi sonra İngilizceyi kendisi seçti
        self.sso(('can', 'Can'))
        self.assertEqual(self.chat.users['can']['language'], 'en')

    def test_deactivated_chat_account_is_refused(self):
        self.chat.users['eski'] = {'_id': 'id-eski', 'username': 'eski', 'name': 'Eski', 'active': False, 'roles': ['user']}
        self.assertEqual(self.sso(('eski', 'Eski'))[0][0], 403)

    def test_portal_permission_read_uses_the_session_cookie_and_caller_token(self):
        seen = {}

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return json.dumps(seen['body']).encode()

        def urlopen(request, timeout=None):
            seen['url'], seen['headers'] = request.full_url, dict(request.header_items())
            return Reply()

        self.patches[2].stop()
        try:
            with patch.object(login, 'BRIDGE_CALLER_TOKEN', 'arayan'), patch.object(login.urllib.request, 'urlopen', urlopen):
                seen['body'] = {'isAdmin': False, 'perms': ['sayfa:kampus', 'ozellik:sohbet.yonet']}
                self.assertIs(login.portal_can_manage_chat('abc'), True)
                self.assertEqual(seen['url'], login.BRIDGE_URL + '/api/v1/access/me')
                self.assertEqual(seen['headers']['Cookie'], f'{login.COOKIE}=abc')
                self.assertEqual(seen['headers']['X-semantic-caller'], 'arayan')
                seen['body'] = {'isAdmin': True, 'perms': []}
                self.assertIs(login.portal_can_manage_chat('abc'), True)
                seen['body'] = {'isAdmin': False, 'perms': ['sayfa:kampus']}
                self.assertIs(login.portal_can_manage_chat('abc'), False)
                seen['body'] = {'detail': 'caller token required'}
                self.assertIsNone(login.portal_can_manage_chat('abc'))
            self.assertIsNone(login.portal_can_manage_chat(None))
        finally:
            self.patches[2].start()


if __name__ == '__main__':
    unittest.main()
