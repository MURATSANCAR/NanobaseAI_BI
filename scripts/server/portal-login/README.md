# Timaş portal login

The public SPA renders a themed login form. Financial API routes require an
nginx `auth_request` to the loopback session adapter. Existing Basic API clients
remain compatible; the browser uses Secure, HttpOnly, SameSite=Strict cookies.
Sessions are random opaque tokens, hashed in SQLite, expire after eight hours,
and are deleted on logout. State-changing cookie requests require the portal
Origin. Password validation uses the existing nginx htpasswd file unchanged.

## Runtime files

- `/opt/timas-login/server.py`, installed from this directory.
- `/etc/systemd/system/timas-login.service`, installed from this directory.
- `/var/lib/timas-login/sessions.sqlite`, managed by the service.
- `/etc/nanobase/timas-test-invite.json`, root:www-data, mode 0640. Contains
  `token`, `username`, `password`, and Unix `expires`. Never commit this file.
- `/etc/nginx/timas-auth-ok.txt`: readable static text `ok`, used only by the
  loopback password verifier on port 8797. The adapter binds port 8796.

An invitation URL has `/timas/#test=<random-secret>`. The fragment is removed
immediately and exchanged in a request header. It is not sent in access-log
URLs or stored in localStorage. Only holders of an unexpired invitation receive
prefilled credentials; normal visitors see empty fields. This is shared account
access to real data: share only with the intended test team. Expiring/removing
the invitation prevents new prefills, but does not revoke copied passwords or
existing sessions. Revoke the test account separately when testing ends.

## Deployment

Build `apps/cockpit` with `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas` and sync
`dist/` to `/data/nanobaseai/bi/cockpit/dist/`. Keep old hashed assets during
rollout. Install the service and runtime files above, then enable/start
`timas-login`. Run `configure_nginx.py` with sudo once; it backs up the site,
tests nginx configuration, and reloads. It changes only Timaş routes and adds
the local verifier. Subsequent service updates require a restart. Do not rerun
the legacy `deploy-timas-auth.sh`: it provisions Basic-only auth and overwrites
the existing password file.

Rollback: restore the nginx backup printed by the configurator and the previous
cockpit `index.html`, run `nginx -t`, then reload nginx. Existing htpasswd users
are preserved throughout. Stop `timas-login` after restoring Basic-only routes.

## Verification

Run `python3 scripts/server/portal-login/test_server.py`: cookie attributes,
login/logout/revocation, expiry, invalid password, cross-origin denial, and
invitation expiry. Live release checks must also validate the real nginx
password verifier and protected API routes; mocked unit tests alone do not
establish that integration. Verify normal and invited browser entrances,
responsive layout, login, and logout.
