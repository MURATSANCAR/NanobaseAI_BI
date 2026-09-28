#!/usr/bin/env python3
"""Portal nginx'ine M19 Pazarlama görsel ve metin ekranının iki özel konumunu ekler (idempotent; add-freelance-routes.py kalıbı).

1. Varlık önizlemeleri ve dosyaları (GET): talep ekranı ve arşiv bir açılışta onlarca görsel ister; genel /timas/api/
   sınırına (dakikada 120) takılmasın diye stüdyo görselleriyle aynı bölge (timas_studio_img).
2. Kapak (25 MB) ve marka kiti dosyası (20 MB) yüklemesi (PUT); genel gövde sınırı 10 MB. Gövde tamponlanmadan akar.

Müşteri VM'inde aynı iki konum `infra/docker/bi/web.default.conf.template`'te. `nginx -t` geçmezse dosya eski içeriğine döner.

Test sunucusunda:  sudo python3 add-marketing-creative-routes.py
"""
import os
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
s = open(P, encoding="utf-8").read()
if "marketing/creative/(assets" in s:
    print("zaten var")
    sys.exit(0)
loc_anchor = "    location /timas/api/ {\n"
if loc_anchor not in s or "zone=timas_studio_img" not in s:
    print("beklenen satırlar bulunamadı (genel API konumu ya da stüdyo görsel bölgesi); dokunulmadı")
    sys.exit(1)
loc = r'''    # M19 Pazarlama görsel ve metin: varlık önizlemeleri ve dosyaları.
    location ~ "^/timas/api/v1/marketing/creative/(assets/[0-9a-f]{32}/file|requests/MC-[0-9]{4}-[0-9]{4,}/cover|brand/files/[0-9a-f]{32})$" {
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

    # M19 kapak (25 MB) ve marka kiti dosyası (20 MB) yüklemesi; genel API gövde sınırı 10 MB.
    location ~ "^/timas/api/v1/marketing/creative/(requests/MC-[0-9]{4}-[0-9]{4,}/cover|brand/files)$" {
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
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        client_max_body_size 26M;
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
