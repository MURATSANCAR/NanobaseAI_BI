"""Run with sudo after installing the session adapter. Backs up before editing."""
import pathlib
import re
import shutil
import subprocess
import time

site = pathlib.Path('/etc/nginx/sites-enabled/portal.nanobase.ai').resolve()
original = site.read_text()
if '# timas-session-login' in original:
    raise SystemExit('Session login already configured; no change.')
backup = pathlib.Path('/etc/nginx/backups') / ('portal.before-login-' + str(int(time.time())))
backup.parent.mkdir(exist_ok=True)
shutil.copy2(site, backup)

s = original
# Change only Timaş blocks. Unrelated applications and bridge caller headers stay intact.
def replace_block(match):
    block = match[0]
    block = re.sub(r'\s*auth_basic(?:_user_file)? [^;]+;', '', block)
    if '/timas/api/' in block:
        block = block.replace('{', '{\n        set $timas_original_method $request_method;\n        auth_request /_timas_session_check;', 1)
    return block
s = re.sub(r'    location (?:~ \^/timas/api/v1/ask\(_agent\)\?\$|/timas/api/|/timas/) \{[^}]+\}', replace_block, s)
locations = '''
    # timas-session-login
    location = /_timas_session_check {
        internal;
        proxy_pass http://127.0.0.1:8796/check;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-Method $timas_original_method;
        proxy_set_header Cookie $http_cookie;
        proxy_set_header Authorization $http_authorization;
        proxy_set_header Origin $http_origin;
    }
    location ^~ /timas/auth/ {
        limit_req zone=timas_login burst=10 nodelay;
        limit_req_status 429;
        client_max_body_size 4k;
        proxy_pass http://127.0.0.1:8796/;
        proxy_set_header Origin $http_origin;
        proxy_set_header Cookie $http_cookie;
        proxy_set_header X-Test-Invite $http_x_test_invite;
        proxy_hide_header X-Powered-By;
    }
'''
s = s.replace('    location = /timas {', locations + '\n    location = /timas {', 1)
s = 'limit_req_zone $binary_remote_addr zone=timas_login:10m rate=20r/m;\n' + s
s += '''
# The password verifier is reachable only on loopback, never from the internet.
server {
    listen 127.0.0.1:8797;
    server_name localhost;
    access_log off;
    location = /verify {
        auth_basic "Portal verifier";
        auth_basic_user_file /etc/nginx/htpasswd-timas;
        alias /etc/nginx/timas-auth-ok.txt;
    }
    location / { return 404; }
}
'''
site.write_text(s)
try:
    subprocess.run(['nginx', '-t'], check=True)
    subprocess.run(['nginx', '-s', 'reload'], check=True)
except Exception:
    shutil.copy2(backup, site)
    subprocess.run(['nginx', '-t'], check=True)
    raise
print('Configured; rollback file:', backup)
