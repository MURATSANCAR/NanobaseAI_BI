#!/usr/bin/env python3
"""GPU genel nginx'ine Kitap Eczanesi'nin kart servisi yollarını ekler (EDITOR bloğunun içine, idempotent).

Kitap Eczanesi (2026-10-02; portal `/timas/kitap-eczanesi`, köprü `editorial_pharmacy.py`) kart servisinin dört
yeni ucunu kullanır. Test sunucusu kart servisine tünelle doğrudan gider; müşteri VM'i bu nginx üzerinden gelir ve
beyaz listede olmayan yol varsayılan siteye düşer (200 + HTML → köprüde 502).

- `GET  /editor/cards/v1/archive/books`                       → liste (arama, süzgeç, sayfa: sorgu dizgisi geçer)
- `GET  /editor/cards/v1/archive/books/<uuid>`                → tek kitap
- `POST /editor/cards/v1/books/<uuid>/redaction`              → kitabı redaksiyona aç (X-Editor köprüden)
- `POST /editor/cards/v1/books/<uuid>/proofing/word-variety/alternatives` → karşılık önerileri (model; 660 sn)

`add-review-routes.py` ile aynı üç kat koruma: kaynak ağ (`customer_sources.ALLOW`), gizli başlık, yöntem sınırı.
Kimlik desende UUID'e sınırlı; serbest yol parçası proxy'ye geçmez. Gizli başlık değeri mevcut bloktan okunur,
dosyaya yeni sır yazılmaz. `nginx -t` geçmezse dosya eski içeriğine döner ve nginx yeniden yüklenmez.

GPU'da çalıştırılır:  sudo python3 add-pharmacy-routes.py
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from customer_sources import ALLOW  # noqa: E402 — müşteri kaynak adresleri tek yerde

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
if "EDITOR-ECZANE" in s:
    print("zaten var")
    sys.exit(0)
if "EDITOR-BITTI" not in s:
    print("EDITOR bloğu bulunamadı; önce add-cards-routes.py koşmalı")
    sys.exit(1)
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', s).group(1)
guard = f'''        {ALLOW}
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}'''
uuid = "[0-9a-fA-F-]{36}"
block = f'''    # EDITOR-ECZANE  (musteri VM -> Kitap Eczanesi: arsiv listesi, tek kitap, redaksiyona acma, karsilik onerisi)
    location = /editor/cards/v1/archive/books {{
{guard}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/archive/books$is_args$args;
        proxy_set_header Host $host;
    }}
    location ~ "^/editor/cards/v1/archive/books/({uuid})$" {{
{guard}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/archive/books/$1;
        proxy_set_header Host $host;
    }}
    location ~ "^/editor/cards/v1/books/({uuid})/redaction$" {{
{guard}
        if ($request_method != POST) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/books/$1/redaction;
        proxy_set_header Host $host;
    }}
    location ~ "^/editor/cards/v1/books/({uuid})/proofing/word-variety/alternatives$" {{
{guard}
        if ($request_method != POST) {{ return 405; }}
        proxy_read_timeout 660s;
        proxy_send_timeout 660s;
        proxy_pass http://127.0.0.1:19141/v1/books/$1/proofing/word-variety/alternatives;
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
