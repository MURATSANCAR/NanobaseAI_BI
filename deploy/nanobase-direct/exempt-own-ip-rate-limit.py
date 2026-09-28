#!/usr/bin/env python3
"""Portal nginx'inde test sunucusunun kendi adresini API hız sınırından muaf tutar (idempotent).

Sınır IP başınadır (timas_api: dakikada 120, 30 anlık; stüdyo görselleri ayrı). Oturumların tarayıcı testleri
sunucunun kendisinde koşar ve portala dış adresten (38.247.162.28) gelir; hepsi tek kotayı paylaşıp 429 alıyordu
(2026-09-28: SEO iş listesi ekran testi Editoryal ön yükleme isteklerinde 429). Muafiyet yalnız sunucunun kendi
adresine ve 127.0.0.1'e; dışarıdaki her kullanıcı eskisi gibi sınırlanır. Giriş (timas_login) ve LLM (timas_ask)
sınırları muaf değildir. Anahtarı boş olan istek nginx'te sınıra sayılmaz. `nginx -t` geçmezse dosya eski içeriğine
döner; nginx yeniden başlatılmaz, yalnız reload.

Test sunucusunda:  sudo python3 exempt-own-ip-rate-limit.py
"""
import os
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
OWN = ("127.0.0.1", "38.247.162.28")
s = open(P, encoding="utf-8").read()
if "$timas_rl_key" in s:
    print("zaten var")
    sys.exit(0)
zones = {
    "limit_req_zone $binary_remote_addr zone=timas_api:10m rate=120r/m;\n":
        "limit_req_zone $timas_rl_key zone=timas_api:10m rate=120r/m;\n",
    "limit_req_zone $binary_remote_addr zone=timas_studio_img:10m rate=600r/m;\n":
        "limit_req_zone $timas_rl_key zone=timas_studio_img:10m rate=600r/m;\n",
}
if any(old not in s for old in zones):
    print("beklenen satırlar bulunamadı; dokunulmadı")
    sys.exit(1)
head = ("# Sunucunun kendi adresi (oturumların tarayıcı testleri) API hız sınırına sayılmaz; boş anahtar = sınır yok.\n"
        "geo $timas_rl_own {\n    default 0;\n" + "".join(f"    {ip} 1;\n" for ip in OWN) + "}\n"
        "map $timas_rl_own $timas_rl_key {\n    1 \"\";\n    default $binary_remote_addr;\n}\n")
new = s
for old, rep in zones.items():
    new = new.replace(old, rep, 1)
new = head + new
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi, nginx reload tamam")
