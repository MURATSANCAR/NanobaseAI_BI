#!/usr/bin/env python3
"""GPU genel nginx'ine Kitap Tasarım Stüdyosu'nun yollarını ekler (EDITOR bloğunun içine, idempotent).

`add-cards-routes.py` ile aynı üç kat koruma: kaynak ağ, gizli başlık, izin verilen yöntem. Stüdyo
servisi (editor-studio, 127.0.0.1:19142) yazar: iş başlatır, resim üretir, sürüm seçer, onaylar. Her
yolun yöntemi tek: okuyanlar GET, yazanlar POST. İş kimliği 14 rakam + 6 onaltılık hane, resim anahtarı
sayfa numarası ya da «kapak», sürüm ve sayfa rakam; serbest yol parçası proxy'ye geçmez. Word yükleme
yolunda gövde sınırı 25 MB (servis 20 MB'tan büyüğünü reddeder).

Düzenleyen kişi köprünün `X-Editor` başlığından okunur; nginx başlığı olduğu gibi geçirir. Gizli başlık
değeri mevcut bloktan okunur, dosyaya yeni sır yazılmaz. `nginx -t` geçmezse dosya eski içeriğine döner.

GPU'da çalıştırılır:  sudo python3 add-studio-routes.py
"""
import os
import re
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
if "EDITOR-STUDYO" in s:
    print("zaten var")
    sys.exit(0)
if "EDITOR-BITTI" not in s:
    print("EDITOR bloğu bulunamadı; önce add-cards-routes.py koşmalı")
    sys.exit(1)
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', s).group(1)
guard = f'''        allow 85.105.0.0/16; deny all;
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}'''
JOB = "[0-9]{14}[0-9a-f]{6}"
KEY = "[0-9]{1,4}|kapak"
UP = "http://127.0.0.1:19142/v1/studio"


def loc(pattern: str, method: str, target: str, extra: str = "") -> str:
    return f'''    location ~ "^/editor/studio/v1/studio/{pattern}$" {{
{guard}
        if ($request_method != {method}) {{ return 405; }}{extra}
        proxy_pass {UP}/{target};
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }}
'''


# Aynı yolda GET ve POST olan tek uç: /jobs (liste ve yeni iş). nginx'te yöntem başına ayrı location
# yazılamadığı için ikisine izin veren ayrı blok.
jobs = f'''    location = /editor/studio/v1/studio/jobs {{
{guard}
        if ($request_method !~ ^(GET|POST)$) {{ return 405; }}
        proxy_pass {UP}/jobs;
        proxy_set_header Host $host;
    }}
'''
block = ("    # EDITOR-STUDYO  (musteri VM -> kitap tasarim studyosu; ayni uc kat koruma)\n" + jobs
         # regex location'da proxy_pass sabit URI taşıyamaz; yol parçası yakalanıp değişkenle verilir
         + loc("jobs/(docx)", "POST", "jobs/$1", "\n        client_max_body_size 25m;")
         + loc(f"jobs/({JOB})", "GET", "jobs/$1")
         + loc(f"jobs/({JOB})/restart", "POST", "jobs/$1/restart")
         + loc(f"jobs/({JOB})/pages/([0-9]{{1,4}})/preview", "GET", "jobs/$1/pages/$2/preview$is_args$args")
         + loc(f"jobs/({JOB})/cover/preview", "GET", "jobs/$1/cover/preview$is_args$args")
         + loc(f"jobs/({JOB})/art/({KEY})/([0-9]{{1,3}})", "GET", "jobs/$1/art/$2/$3$is_args$args")
         + loc(f"jobs/({JOB})/art/({KEY})/(regenerate|select|approve)", "POST", "jobs/$1/art/$2/$3")
         + loc(f"jobs/({JOB})/characters/([0-9]{{1,2}})", "GET", "jobs/$1/characters/$2$is_args$args")
         + loc(f"jobs/({JOB})/pdf/(ic|kapak)", "GET", "jobs/$1/pdf/$2"))
open(P, "w", encoding="utf-8").write(s.replace("    # EDITOR-BITTI", block + "    # EDITOR-BITTI", 1))
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi, nginx reload tamam")
