#!/usr/bin/env python3
"""Portal nginx'ine Zeki AI sesli not ucu için ayrı konum ekler (idempotent).

Telefon kaydı 16 kHz WAV'a çevrilip gönderilir: 5 dakika ≈ 9,6 MB, genel /timas/api/ gövde sınırı 10 MB. Köprü
`VOICE_NOTE_MAX_MB`'ı (varsayılan 20) kendisi uygular; burada 21 MB. Ses nginx'in geçici dosyasına yazılmasın diye
istek tamponu kapalı (`proxy_request_buffering off`: gövde geldikçe köprüye akar). Oturum denetimi, hız sınırı ve
arayan başlığı genel API ile aynı. `nginx -t` geçmezse dosya eski içeriğine döner.

Test sunucusunda:  sudo python3 add-voice-note-route.py
"""
import os
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
s = open(P, encoding="utf-8").read()
loc_anchor = "    location /timas/api/ {\n"
if loc_anchor not in s:
    print("beklenen satır bulunamadı; dokunulmadı")
    sys.exit(1)
if "/timas/api/v1/voice-note" in s:
    print("zaten var")
    sys.exit(0)
block = r'''    # Zeki AI sesli not: telefon kaydı (WAV) yükleme; ses diske tamponlanmaz.
    location = /timas/api/v1/voice-note {
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
        proxy_read_timeout 420s;
        client_max_body_size 21M;
    }

'''
open(P, "w", encoding="utf-8").write(s.replace(loc_anchor, block + loc_anchor, 1))
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi — nginx reload tamam")
