#!/usr/bin/env python3
"""Portal nginx'ine Serbest çalışanlar ekranının iki özel konumunu ekler (idempotent).

1. Portfolyo görselleri (GET): kişi listesi ve kartı bir açılışta onlarca küçük görsel ister; genel /timas/api/
   sınırına (dakikada 120) takılmasın diye stüdyo görselleriyle aynı bölge (timas_studio_img, dakikada 600).
2. Portfolyo ve teslim yüklemesi (PUT): köprü portfolyoda 40 MB, teslimde 200 MB kabul eder; genel gövde sınırı
   10 MB. Gövde tamponlanmadan köprüye akar (proxy_request_buffering off).

Oturum denetimi (auth_request) ve arayan başlığı genel API ile aynı. Stüdyo görsel bölgesi yoksa (add-studio-image-limit.py
koşmamışsa) önce o eklenmeli. `nginx -t` geçmezse dosya eski içeriğine döner.

Test sunucusunda:  sudo python3 add-freelance-routes.py
"""
import os
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
s = open(P, encoding="utf-8").read()
if "editorial/freelance/portfolio" in s:
    print("zaten var")
    sys.exit(0)
loc_anchor = "    location /timas/api/ {\n"
if loc_anchor not in s or "zone=timas_studio_img" not in s:
    print("beklenen satırlar bulunamadı (genel API konumu ya da stüdyo görsel bölgesi); dokunulmadı")
    sys.exit(1)
loc = r'''    # Serbest çalışan portfolyo görselleri: liste ve kart bir açılışta onlarca görsel ister.
    location ~ "^/timas/api/v1/editorial/freelance/portfolio/[0-9a-f]{32}$" {
        if ($request_method != GET) { return 405; }
        set $timas_original_method $request_method;
        auth_request /_timas_session_check;
        limit_req zone=timas_studio_img burst=120 nodelay;
        limit_req_status 429;
        rewrite ^/timas/(.*)$ /$1 break;
        include /etc/nginx/snippets/timas-semantic-caller.conf;
        proxy_pass http://127.0.0.1:8795;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Connection "";
        proxy_read_timeout 120s;
    }

    # Serbest çalışan portfolyo (40 MB) ve teslim (200 MB) yüklemesi; genel API gövde sınırı 10 MB.
    location ~ "^/timas/api/v1/editorial/freelance/(people/[0-9a-f]{32}/portfolio|tasks/[0-9a-f]{32}/delivery)$" {
        if ($request_method != PUT) { return 405; }
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
        proxy_request_buffering off;
        proxy_read_timeout 900s;
        proxy_send_timeout 900s;
        client_max_body_size 201M;
    }

'''
new = s.replace(loc_anchor, loc + loc_anchor, 1)
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi, nginx reload tamam")
