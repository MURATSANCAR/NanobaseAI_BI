#!/usr/bin/env python3
"""GPU genel nginx'ine merkezi denetim kaydının iki yolunu ekler (EDITOR bloğunun içine, idempotent).

Portal köprüsü (`audit_trail.pull_editor`) editörün giden kutusunu kart servisinden çeker: `GET /v1/audit/outbox` ve
`POST /v1/audit/outbox/ack` (apps/editor/src/editor/audit.py). Test sunucusu kart servisine tünelle gider; müşteri
VM'i bu nginx üzerinden gelir ve yol beyaz listede değilse 405 alır.

`add-read-route.py` ile aynı koruma: kaynak ağ (`customer_sources.ALLOW`), gizli başlık, yöntem sınırı; kart servisi
ayrıca Bearer anahtarını ister. Gizli başlık değeri mevcut bloktan okunur. `nginx -t` geçmezse dosya eski içeriğine döner.

GPU'da çalıştırılır:  sudo python3 add-audit-routes.py
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from customer_sources import ALLOW  # noqa: E402 — müşteri kaynak adresleri tek yerde

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
if "EDITOR-DENETIM" in s:
    print("zaten var")
    sys.exit(0)
if "EDITOR-BITTI" not in s:
    print("EDITOR bloğu bulunamadı; önce add-cards-routes.py koşmalı")
    sys.exit(1)
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', s).group(1)
block = f'''    # EDITOR-DENETIM  (musteri VM -> merkezi denetim kaydi: editorun giden kutusu; GET liste, POST onay)
    location = /editor/cards/v1/audit/outbox {{
        {ALLOW}
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != GET) {{ return 405; }}
        proxy_read_timeout 120s;
        proxy_pass http://127.0.0.1:19141/v1/audit/outbox;
        proxy_set_header Host $host;
    }}
    location = /editor/cards/v1/audit/outbox/ack {{
        {ALLOW}
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != POST) {{ return 405; }}
        proxy_pass http://127.0.0.1:19141/v1/audit/outbox/ack;
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
