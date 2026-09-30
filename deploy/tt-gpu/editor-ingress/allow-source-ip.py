#!/usr/bin/env python3
"""GPU genel nginx'inde müşteri VM'ine açılan her yola (kitap kartları, BI tahmin) bir kaynak adres ekler (idempotent).

Müşteri ağına izin veren her `allow 85.105.0.0/16;` satırının önüne `allow <adres>;` koyar; başka koruma (gizli başlık,
yöntem) değişmez. `nginx -t` geçmezse dosya eski içeriğine döner. GPU'da:  sudo python3 allow-source-ip.py 212.156.126.250/32

2026-09-25: TİMAŞ'ın internet çıkışı 85.105.155.33'ten 212.156.126.250'ye (ikinci hat, WatchGuard) geçti; VM'in
istekleri 403 aldı. Adres yalnız /32 olarak eklenir.
"""
import ipaddress
import os
import re
import subprocess
import sys

net = str(ipaddress.ip_network(sys.argv[1], strict=True))  # geçersiz adres burada durur
P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
s = open(P, encoding="utf-8").read()
anchor = "allow 85.105.0.0/16;"
new_line = f"allow {net}; {anchor}"
if anchor not in s:
    print("müşteri ağı satırı bulunamadı"); sys.exit(1)
# Her yol ayrı denetlenir: adres bir yolda varsa öteki yollar da var sayılmaz. Eski sürüm «zaten var» deyip çıkıyordu;
# 2026-09-25'ten sonra kurulan 99 yol adresi hiç almadı (VM'de stüdyo ekranları 403).
out = re.sub(rf"(?<!allow {re.escape(net)}; ){re.escape(anchor)}", new_line, s)
missing = s.count(anchor) - s.count(new_line)
if out == s:
    print(f"zaten var ({s.count(new_line)} yolda)"); sys.exit(0)
open(P, "w", encoding="utf-8").write(out)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr); sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print(f"{missing} yola {net} eklendi (toplam {out.count(new_line)}), nginx reload tamam")
