#!/usr/bin/env python3
"""Portal nginx'ine stüdyonun ses kütüphanesi yükleme ucu için 250 MB gövde sınırı ekler (idempotent).

«Ses yükle» gövdesi base64 JSON'dur: normalleştirilmiş kayıt + yüklenen özgün ses dosyası + izin belgesi (servis dosya
başına STUDIO_UPLOAD_MB uygular, köprü gövdeyi 250 MB'ta keser). Genel /timas/api/ gövde sınırı 10 MB olduğu için büyük
belge ya da uzun wav kaydı nginx'te 413 alırdı. Yalnız bu uç: oturum denetimi (auth_request), hız sınırı ve arayan
başlığı genel API ile aynı. `nginx -t` geçmezse dosya eski içeriğine döner.

Test sunucusunda:  sudo python3 add-studio-voice-size.py
"""
import os
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
s = open(P, encoding="utf-8").read()
if "/timas/api/v1/editorial/studio/voices" in s:
    print("zaten var")
    sys.exit(0)
loc_anchor = "    location /timas/api/ {\n"
if loc_anchor not in s:
    print("beklenen satır bulunamadı; dokunulmadı")
    sys.exit(1)
loc = r'''    # Stüdyo ses kütüphanesine ses yükleme (kayıt + özgün dosya + izin belgesi, base64 JSON); genel API sınırı 10 MB.
    location = /timas/api/v1/editorial/studio/voices {
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
        client_max_body_size 250M;
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
