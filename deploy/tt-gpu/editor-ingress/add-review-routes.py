#!/usr/bin/env python3
"""GPU genel nginx'ine inceleme kuyruğunun yollarını ekler (EDITOR bloğunun içine, idempotent).

`add-cards-routes.py` ile aynı üç kat koruma: kaynak ağ, gizli başlık, izin verilen yöntem. Fark: bu
uçlardan biri YAZAR (karar), dolayısıyla tek POST yolu burada açılıyor ve yalnız o yolda POST kabul
ediliyor; kalan üç yol salt okunur. Kitap ve kayıt kimlikleri desende UUID'e, sayfa numarası rakama
sınırlı — serbest yol parçası proxy'ye geçmez.

Kararı veren kişi köprünün `X-Editor` başlığından okunur; nginx başlığı olduğu gibi geçirir (varsayılan
davranış), üretmez. Gizli başlık değeri mevcut bloktan okunur, dosyaya yeni sır yazılmaz. `nginx -t`
geçmezse dosya eski içeriğine döner ve nginx yeniden yüklenmez.

GPU'da çalıştırılır:  sudo python3 add-review-routes.py
"""
import os
import re
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
if "EDITOR-INCELEME" in s:
    print("zaten var")
    sys.exit(0)
if "EDITOR-BITTI" not in s:
    print("EDITOR bloğu bulunamadı; önce add-cards-routes.py koşmalı")
    sys.exit(1)
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', s).group(1)
guard = f'''        allow 85.105.0.0/16; deny all;
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}'''
uuid = "[0-9a-fA-F-]{36}"
block = f'''    # EDITOR-INCELEME  (musteri VM -> inceleme kuyrugu; uc GET + bir POST, ayni uc kat koruma)
    location ~ "^/editor/cards/v1/books/({uuid})/review$" {{
{guard}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/$1/review$is_args$args;
        proxy_set_header Host $host;
    }}
    location ~ "^/editor/cards/v1/books/({uuid})/review/decide-many$" {{
{guard}
        if ($request_method != POST) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/$1/review/decide-many;
        proxy_set_header Host $host;
    }}
    location ~ "^/editor/cards/v1/books/({uuid})/pages/([0-9]{{1,5}})$" {{
{guard}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/$1/pages/$2;
        proxy_set_header Host $host;
    }}
    location ~ "^/editor/cards/v1/books/({uuid})/pages/([0-9]{{1,5}})/context$" {{
{guard}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/$1/pages/$2/context;
        proxy_set_header Host $host;
    }}
    location ~ "^/editor/cards/v1/books/({uuid})/figures/({uuid})$" {{
{guard}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/$1/figures/$2;
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
