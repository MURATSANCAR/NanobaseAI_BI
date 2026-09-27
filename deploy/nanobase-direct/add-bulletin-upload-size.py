#!/usr/bin/env python3
"""Portal nginx'ine Kampüs sesli bülten yükleme ucu için 61 MB gövde sınırı ekler (idempotent).

Köprü 60 MB'a kadar ses kabul eder (`BULLETIN_MAX_MB`); genel /timas/api/ gövde sınırı 10 MB olduğu için
14 dakikalık bir mp3 bile nginx'te 413 alırdı. Yalnız bu uç (yönetici yüklemesi; köprü yöneticiyi ayrıca
denetler): oturum denetimi, hız sınırı ve arayan başlığı genel API ile aynı; yükleme uzun sürebileceği için
okuma süresi 300 sn. `nginx -t` geçmezse dosya eski içeriğine döner.

Test sunucusunda:  sudo python3 add-bulletin-upload-size.py
"""
import os
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
s = open(P, encoding="utf-8").read()
orig = s

# Oturum denetimi iç isteği gövdeyi geçirmez, ama kendi gövde sınırı varsayılan 1 MB'tır: büyük yüklemede
# 413 alır ve auth_request bunu 500'e çevirir (VM şablonunda bu satır var, test sunucusunda yoktu).
check_anchor = "    location = /_timas_session_check {\n        internal;\n"
if check_anchor in s and "client_max_body_size 0;" not in s.split(check_anchor, 1)[1].split("}", 1)[0]:
    s = s.replace(check_anchor, check_anchor + "        client_max_body_size 0;\n", 1)

if "api/v1/admin/bulletins" in s:
    if s != orig:
        open(P, "w", encoding="utf-8").write(s)
        t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
        if t.returncode != 0:
            open(P, "w", encoding="utf-8").write(orig)
            print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
            sys.exit(1)
        subprocess.run(["systemctl", "reload", "nginx"], check=True)
        print("oturum denetimine gövde sınırı eklendi, nginx reload tamam")
    else:
        print("zaten var")
    sys.exit(0)
loc_anchor = "    location /timas/api/ {\n"
if loc_anchor not in s:
    print("beklenen satır bulunamadı; dokunulmadı")
    sys.exit(1)
loc = r'''    # Kampüs sesli bülteni yükleme: köprü 60 MB'a kadar ses kabul eder; genel API gövde sınırı 10 MB.
    location = /timas/api/v1/admin/bulletins {
        set $timas_original_method $request_method;
        auth_request /_timas_session_check;
        limit_req zone=timas_api burst=30 nodelay;
        limit_req_status 429;
        rewrite ^/timas/(.*)$ /$1 break;
        include /etc/nginx/snippets/timas-semantic-caller.conf;
        proxy_pass http://127.0.0.1:8795;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Connection "";
        proxy_read_timeout 300s;
        client_max_body_size 61M;
    }

'''
new = s.replace(loc_anchor, loc + loc_anchor, 1)
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(orig)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi, nginx reload tamam")
