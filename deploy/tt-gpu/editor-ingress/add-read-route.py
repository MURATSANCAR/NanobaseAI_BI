#!/usr/bin/env python3
"""GPU genel nginx'ine portal belge okuma yolunu ekler (EDITOR bloğunun içine, idempotent).

Köprünün ortak belge okuyucusu (`backend/semantic_bridge/doc_read.py`) taranmış PDF sayfasını ve fotoğrafı kart
servisinin `POST /v1/read` ucuna gönderir (docs/analiz/ai-firsatlari/BELGE-OKUMA.md). Test sunucusu kart servisine
tünelle doğrudan gider; müşteri VM'i bu nginx üzerinden gelir ve yol beyaz listede olmadığı için 405 alıyordu
(2026-09-29 ölçümü: sözleşme karşılaştırmada telefon fotoğrafı yüklenip okunamıyordu).

`add-review-routes.py` ile aynı üç kat koruma: kaynak ağ (`customer_sources.ALLOW`), gizli başlık, yalnız POST.
Gövde sınırı yok (şartname, rapor; portal kendi sınırını uygular), OCR modeli açılırken beklenir diye süre 960 sn
(köprünün `DOC_READ_TIMEOUT_SEC` üst sınırı 900). Gizli başlık değeri mevcut bloktan okunur, dosyaya yeni sır
yazılmaz. `nginx -t` geçmezse dosya eski içeriğine döner ve nginx yeniden yüklenmez.

GPU'da çalıştırılır:  sudo python3 add-read-route.py
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from customer_sources import ALLOW  # noqa: E402 — müşteri kaynak adresleri tek yerde

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
if "EDITOR-OKUMA" in s:
    print("zaten var")
    sys.exit(0)
if "EDITOR-BITTI" not in s:
    print("EDITOR bloğu bulunamadı; önce add-cards-routes.py koşmalı")
    sys.exit(1)
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', s).group(1)
block = f'''    # EDITOR-OKUMA  (musteri VM -> portal belge okuma: taranmis sayfa / fotograf -> metin; yalniz POST)
    location = /editor/cards/v1/read {{
        {ALLOW}
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != POST) {{ return 405; }}
        client_max_body_size 0;
        proxy_request_buffering off;
        proxy_read_timeout 960s;
        proxy_send_timeout 960s;
        proxy_pass http://127.0.0.1:19141/v1/read;
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
