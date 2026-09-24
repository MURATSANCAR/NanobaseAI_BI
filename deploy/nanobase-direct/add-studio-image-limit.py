#!/usr/bin/env python3
"""Portal nginx'ine Kitap Tasarım Stüdyosu görsellerinin kendi hız sınırını ekler (idempotent).

Genel /timas/api/ sınırı IP başına dakikada 120 istek (30 anlık). Stüdyo ekranı bir açılışta 60'tan fazla
küçük sayfa/resim önizlemesi ister ve 429 alıyordu (2026-09-24). Yalnız stüdyonun GET görsel uçları için
ayrı bölge: dakikada 600, 120 anlık. Oturum denetimi (auth_request) ve arayan başlığı aynen korunur; yöntem
yalnız GET. `nginx -t` geçmezse dosya eski içeriğine döner.

Test sunucusunda:  sudo python3 add-studio-image-limit.py
"""
import os
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
s = open(P, encoding="utf-8").read()
if "timas_studio_img" in s:
    print("zaten var")
    sys.exit(0)
zone_anchor = "limit_req_zone $binary_remote_addr zone=timas_api:10m rate=120r/m;\n"
loc_anchor = "    location /timas/api/ {\n"
if zone_anchor not in s or loc_anchor not in s:
    print("beklenen satırlar bulunamadı; dokunulmadı")
    sys.exit(1)
zone = "limit_req_zone $binary_remote_addr zone=timas_studio_img:10m rate=600r/m;\n"
loc = r'''    # Kitap Tasarım Stüdyosu önizlemeleri: bir açılışta 60+ küçük görsel; genel API sınırına takılmasın.
    location ~ "^/timas/api/v1/editorial/studio/jobs/[0-9a-f]{20}/(pages/[0-9]+/preview|cover/preview|art/[0-9a-z]+/[0-9]+|characters/[0-9]+)$" {
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

'''
new = s.replace(zone_anchor, zone_anchor + zone, 1).replace(loc_anchor, loc + loc_anchor, 1)
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi, nginx reload tamam")
