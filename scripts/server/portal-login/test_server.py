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


if __name__ == '__main__':
    unittest.main()
