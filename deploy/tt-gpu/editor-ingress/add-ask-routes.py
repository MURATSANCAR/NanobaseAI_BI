#!/usr/bin/env python3
"""GPU genel nginx'inde Kitaba sor'u kart servisine bağlar (idempotent).

Müşteri VM'inin Kitaba sor'u 2026-10-03'e kadar sohbet ajanının API'sine (`/editor/v1/chat/completions`,
`/editor/v1/models` → 127.0.0.1:19110) gidiyordu; ajan kaldırıldı. Bu betik:

- o iki yolu siler,
- kart servisine iki yol ekler (aynı IP kısıtı, aynı gizli başlık):
  `POST /editor/cards/v1/books/ask`        → 127.0.0.1:19141/v1/books/ask (soru; okuma süresi 600 sn)
  `GET  /editor/cards/v1/books/ask/books`  → 127.0.0.1:19141/v1/books/ask/books (okunmuş kitap adları)

Gizli başlık değeri mevcut bloktan okunur; dosyaya yeni sır yazılmaz. `nginx -t` geçmezse dosya eski içeriğine
döner ve nginx yeniden yüklenmez. GPU'da çalıştırılır:  sudo python3 add-ask-routes.py
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from customer_sources import ALLOW  # noqa: E402 — müşteri kaynak adresleri tek yerde

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', s).group(1)
out = s
for path in ("/editor/v1/chat/completions", "/editor/v1/models"):
    out = re.sub(r"\n    location = " + re.escape(path) + r" \{.*?\n    \}", "", out, count=1, flags=re.S)
if "EDITOR-KITABA-SOR" not in out:
    block = f'''    # EDITOR-KITABA-SOR  (musteri VM -> Kitaba sor; kart servisi, ayni uc kat koruma)
    location = /editor/cards/v1/books/ask {{
        {ALLOW}
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != POST) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/ask;
        proxy_set_header Host $host;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
    }}
    location = /editor/cards/v1/books/ask/books {{
        {ALLOW}
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/ask/books;
        proxy_set_header Host $host;
    }}
'''
    out = out.replace("    # EDITOR-BITTI", block + "    # EDITOR-BITTI", 1)
if out == s:
    print("zaten güncel")
    sys.exit(0)
open(P, "w", encoding="utf-8").write(out)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("güncellendi, nginx reload tamam")
