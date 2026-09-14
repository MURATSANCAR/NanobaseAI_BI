# Timaş portal login

The public SPA renders a themed login form. Financial API routes require an
nginx `auth_request` to the loopback session adapter. The browser uses Secure,
HttpOnly, SameSite=Strict cookies. Sessions are random opaque tokens, hashed in
SQLite, expire after eight hours, and are deleted on logout. State-changing
cookie requests require the portal Origin.

Timaş Active Directory is the only password verifier. There is no demo, local,
htpasswd or Basic-auth account: every enabled AD user signs in with their own
Windows account name (`ali`, `TIMAS\ali` or `ali@timas.local`) and password.

## Active Directory

- `/etc/nanobase/timas-ad.json`, root:www-data, mode 0640. Never commit it:
  `{"host": "192.168.0.20", "port": 389, "netbios": "TIMAS", "dns_domain": "timas.local",
  "base_dn": "DC=timas,DC=local", "bind_user": "<service account>", "bind_password": "<secret>"}`.
- The service account only looks the person up (enabled `person` with that
  `sAMAccountName`); the password is then checked by an NTLM bind as that person.
  NTLM, because the domain controller has no certificate (636 and StartTLS fail)
  and a simple bind would send the password in clear text.
- The domain controller is reached over the server's WatchGuard VPN (`tun0`).
  VPN down, or the configuration file missing → login answers 503
  "Active Directory'ye ulaşılamıyor", never 401.
- Session `username` is the AD account name (personal boards key on it);
  `displayName` is what the screens greet with.
- Wrong passwords count against the person's AD lockout policy. nginx limits
  `/timas/auth/` to 20 requests a minute per IP (burst 10).

## Runtime files

- `/opt/timas-login/server.py`, installed from this directory.
- `/opt/timas-login/venv`, `python3 -m venv` + `pip install -r requirements.txt`
  (ldap3; pycryptodome supplies the MD4 that NTLM needs and OpenSSL 3 dropped).
- `/etc/systemd/system/timas-login.service`, installed from this directory.
- `/var/lib/timas-login/sessions.sqlite`, managed by the service. The `display`
  column is added on start; older sessions keep working.

## Deployment

Build the portal with `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas` on the server
and sync `dist/` to `/data/nanobaseai/bi/cockpit/dist/`. Install the runtime
files above, write the AD configuration, then `systemctl daemon-reload` and
restart `timas-login`. `configure_nginx.py` is for a fresh site only (it refuses
to run twice); it adds the session check and the login route.

Removing the old demo account from an existing server: delete its sessions
(`DELETE FROM sessions WHERE username='Timas'`), `/etc/nanobase/timas-test-invite.json`,
`/etc/nginx/htpasswd-timas`, `/etc/nginx/timas-auth-ok.txt`, the loopback
`127.0.0.1:8797` verifier server block and the `Authorization` / `X-Test-Invite`
header lines in the Timaş locations; then `nginx -t` and reload.

## Verification

Run `python3 scripts/server/portal-login/test_server.py`: cookie attributes,
login/logout/revocation, expiry, invalid password, directory unavailable (503),
account-name parsing, empty password, Basic header refused, cross-origin denial.
Mocked tests do not prove the directory: live checks must sign in through
`https://portal.nanobase.ai/timas/auth/login` with a real AD account, reject a
wrong password and an unknown account, and open a protected API route with the
session cookie.
