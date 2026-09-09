import http.client
import importlib.util
import json
import pathlib
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
        login.INVITE = self.tmp.name + '/invite.json'
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

    def test_login_logout_and_cookie_protection(self):
        with patch.object(login, 'verify', return_value='tester'):
            status, headers, _ = self.request('/login', 'POST', {'username': 'tester', 'password': 'secret'}, {'Origin': login.ORIGIN})
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie']
        for flag in ('Secure', 'HttpOnly', 'SameSite=Strict', 'Path=/timas/'):
            self.assertIn(flag, cookie)
        headers = {'Cookie': cookie.split(';')[0], 'Origin': login.ORIGIN}
        self.assertEqual(self.request('/session', headers=headers)[0], 200)
        self.assertEqual(self.request('/check', headers={**headers, 'Origin': 'https://evil.invalid', 'X-Original-Method': 'POST'})[0], 403)
        self.assertEqual(self.request('/logout', 'POST', headers=headers)[0], 200)
        self.assertEqual(self.request('/session', headers=headers)[0], 401)

    def test_invalid_credentials_no_session(self):
        with patch.object(login, 'verify', return_value=None):
            status, headers, _ = self.request('/login', 'POST', {'username': 'bad', 'password': 'bad'}, {'Origin': login.ORIGIN})
        self.assertEqual(status, 401)
        self.assertNotIn('Set-Cookie', headers)
        self.assertEqual(self.request('/check')[0], 401)

    def test_cross_site_login_denied(self):
        self.assertEqual(self.request('/login', 'POST', {}, {'Origin': 'https://evil.invalid'})[0], 403)

    def test_invitation_requires_secret_and_expiration(self):
        config = {'token': 'only-the-invited-know', 'username': 'test', 'password': 'test-only', 'expires': time.time() + 100}
        pathlib.Path(login.INVITE).write_text(json.dumps(config))
        self.assertEqual(self.request('/prefill')[0], 403)
        self.assertEqual(self.request('/prefill', headers={'X-Test-Invite': 'wrong'})[0], 403)
        headers = {'X-Test-Invite': config['token']}
        status, response_headers, _ = self.request('/prefill', headers=headers)
        self.assertEqual(status, 200)
        remembered = {'Cookie': response_headers['Set-Cookie'].split(';')[0]}
        self.assertEqual(self.request('/prefill', headers=remembered)[0], 200)
        config['expires'] = time.time() - 1
        pathlib.Path(login.INVITE).write_text(json.dumps(config))
        self.assertEqual(self.request('/prefill', headers=headers)[0], 403)
        self.assertEqual(self.request('/prefill', headers=remembered)[0], 403)

    def test_expired_session_denied(self):
        with login.connection() as db:
            db.execute('INSERT INTO sessions VALUES (?, ?, ?)', (login.digest('expired'), 'test', time.time() - 1))
        self.assertEqual(self.request('/session', headers={'Cookie': login.COOKIE + '=expired'})[0], 401)


if __name__ == '__main__':
    unittest.main()
