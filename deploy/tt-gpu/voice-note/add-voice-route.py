#!/usr/bin/env python3
"""GPU genel nginx'ine Zeki AI sesli not için iki yol ekler (idempotent): müşteri VM'i → sesli not servisi (GPU 0).

KULLANICI ONAYIYLA ÇALIŞTIRILIR — paylaşılan üretim nginx'i (kitap-eczanesi) değişir. Kitap kartları ve tahminle aynı üç
kat koruma: yalnız müşteri ağı (85.105.0.0/16), gizli başlık (mevcut EDITOR bloğundaki değer; dosyaya yeni sır yazılmaz),
yöntem sınırı; servis ayrıca kendi anahtarını (X-Voice-Token) ister. `nginx -t` geçmezse dosya eski içeriğine döner.

Düzenli ifadeli location yok (tam eşleşme `=`), proxy_pass sorguyu olduğu gibi taşır (max_seconds, context).
Ses gövdesi nginx'te diske yazılmasın diye istek tamponu kapalı (proxy_request_buffering off) ve gövde sınırı 64 MB.

GPU'da:  sudo python3 add-voice-route.py
Geri almak: dosyadaki «# BI-SESLI-NOT» … «# BI-SESLI-NOT-BITTI» bloğu silinir, `nginx -t && systemctl reload nginx`.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from customer_sources import ALLOW  # noqa: E402 — müşteri kaynak adresleri tek yerde

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
if "BI-SESLI-NOT" in s:
    print("zaten var")
    sys.exit(0)
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', s).group(1)
block = f'''    # BI-SESLI-NOT  (musteri VM -> ZEKI AI sesli not; saglik GET ve yaziya dokme POST, ayni uc kat koruma)
    location = /bi-voice/health {{
        {ALLOW}
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != GET) {{ return 405; }}
        proxy_pass http://127.0.0.1:8797/health;
        proxy_set_header Host $host;
    }}
    location = /bi-voice/v1/transcribe {{
        {ALLOW}
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}
        if ($request_method != POST) {{ return 405; }}
        client_max_body_size 64m;
        proxy_request_buffering off;   # ses nginx'in geçici dosyasına yazılmasın
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        proxy_pass http://127.0.0.1:8797/v1/transcribe$is_args$args;
        proxy_set_header Host $host;
    }}
    # BI-SESLI-NOT-BITTI
'''
open(P, "w", encoding="utf-8").write(s.replace("    # EDITOR-BITTI", block + "    # EDITOR-BITTI", 1))
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi, nginx reload tamam")
