#!/usr/bin/env python3
"""GPU genel nginx'ine BI tahmin servisi için iki yol ekler (idempotent): müşteri VM'i → TimesFM 3.0 (GPU 0).

Kitap kartlarıyla aynı üç kat koruma: yalnız müşteri ağı (85.105.0.0/16), gizli başlık (mevcut EDITOR bloğundaki
değer; dosyaya yeni sır yazılmaz), izin verilen yöntem. `nginx -t` geçmezse dosya eski içeriğine döner.
GPU'da çalıştırılır:  sudo python3 add-forecast-route.py
"""
import os
import re
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
if "BI-TAHMIN" in s:
    print("zaten var")
    sys.exit(0)
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', s).group(1)
block = f'''    # BI-TAHMIN  (musteri VM -> ZEKI AI tahmin; yalniz saglik GET ve toplu tahmin POST, ayni uc kat koruma)
    location = /bi-forecast/health {{
        allow 85.105.0.0/16; deny all;
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:8793/health;
        proxy_set_header Host $host;
    }}
    location = /bi-forecast/forecast/batch {{
        allow 85.105.0.0/16; deny all;
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != POST) {{ return 405; }}
        client_max_body_size 64m;      # ~5.200 kitap x 140 ay
        proxy_read_timeout 900s;
        proxy_send_timeout 900s;
        proxy_pass http://127.0.0.1:8793/forecast/batch;
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
