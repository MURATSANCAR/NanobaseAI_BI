#!/usr/bin/env python3
"""GPU genel nginx'ine kitap kartları için iki salt okunur yol ekler (EDITOR bloğunun içine, idempotent).

Gizli başlık değeri mevcut bloktan okunur; dosyaya yeni sır yazılmaz. `nginx -t` geçmezse dosya eski
içeriğine döner ve nginx yeniden yüklenmez. GPU'da çalıştırılır:  sudo python3 add-cards-routes.py
"""
import os
import re
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
if "EDITOR-KARTLAR" in s:
    print("zaten var")
    sys.exit(0)
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', s).group(1)
block = f'''    # EDITOR-KARTLAR  (musteri VM -> kitap kartlari; salt okunur, yalniz GET, ayni uc kat koruma)
    location = /editor/cards/v1/books/cards {{
        allow 85.105.0.0/16; deny all;
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/cards;
        proxy_set_header Host $host;
    }}
    location ~ "^/editor/cards/v1/books/([0-9a-fA-F-]{{36}})/cover$" {{
        allow 85.105.0.0/16; deny all;
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/$1/cover;
        proxy_set_header Host $host;
    }}
'''
open(P, "w", encoding="utf-8").write(s.replace("    # EDITOR-BITTI", block + "    # EDITOR-BITTI", 1))
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi, nginx reload tamam")
