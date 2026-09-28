#!/usr/bin/env python3
"""Portal nginx'inde kapak arşivi görsellerini stüdyo görsel sınırına alır (idempotent).

Kapak arşivi bir sayfada 60 kapak görseli ister; bu uç genel /timas/api/ sınırına (IP başına dakikada 120, 30 anlık)
düşüyordu: 2026-09-28 ölçümünde tek açılışta 40 görsel 429 aldı. Stüdyo önizlemelerinin bölgesi (`timas_studio_img`,
dakikada 600, 120 anlık; add-studio-image-limit.py) kapak görsellerine de uygulanır. Yalnız GET; oturum denetimi ve
arayan başlığı aynen korunur. Kimlik biçimi köprüdeki `editorial_studio_library.CID` ile aynı. `nginx -t` geçmezse
dosya eski içeriğine döner.

Test sunucusunda:  sudo python3 add-cover-image-limit.py
"""
import os
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
s = open(P, encoding="utf-8").read()
if "studio/library/covers/" in s:
    print("zaten var")
    sys.exit(0)
if "zone=timas_studio_img" not in s:
    print("timas_studio_img bölgesi yok; önce add-studio-image-limit.py")
    sys.exit(1)
loc_anchor = "    location /timas/api/ {\n"
if loc_anchor not in s:
    print("beklenen satır bulunamadı; dokunulmadı")
    sys.exit(1)
loc = r'''    # Kapak arşivi görselleri: bir sayfada 60 kapak; genel API sınırına takılmasın.
    location ~ "^/timas/api/v1/editorial/studio/library/covers/[a-z]{2,10}-[A-Za-z0-9_.-]{1,60}/image$" {
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
new = s.replace(loc_anchor, loc + loc_anchor, 1)
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi, nginx reload tamam")
