#!/usr/bin/env python3
"""Portal nginx'ine editoryal kitap/belge yükleme uçları için özel konum ekler (idempotent) — ZEKI-26.

Uçlar (hepsi ham gövde PUT; aynı yollardaki GET'ler de bu konumdan geçer, yöntem denetimi köprüdedir):
- Redaksiyon eser metni `…/editorial/works/<eser>/manuscript`, son okuma provası `…/proof`, dosyadan yeni eser
  `…/editorial/works-from-file`
- Son okuma «Belge yükle ve incelet» `…/editorial/documents`
- Çeviri kaynak metni `…/editorial/translation/jobs-from-file`, `…/editorial/translation/jobs/<iş>/source`

Bunlar genel /timas/api/ konumuna düşüyordu; oradaki 10 MB gövde sınırı kitap PDF'inde nginx'in HTML 413'ünü
döndürüyordu (ekranda «Zeki AI 413»). Köprü artık gövdeyi diske akıtıyor ve boyut tavanı koymuyor (yalnız disk
dolacaksa 507); bu konumda da tavan yok (`client_max_body_size 0`), gövde tamponlanmadan köprüye akar, büyük PDF'in
işlenmesi için zaman aşımı 30 dk. Oturum denetimi, hız sınırı ve arayan başlığı genel API ile aynı.

İlk sürüm (yalnız redaksiyon/son okuma uçları, PUT dışı 405) kuruluysa bu konum yenisiyle değiştirilir; ilk sürüm
provanın GET durum okumasını 405'e düşürüyordu. `nginx -t` geçmezse dosya eski içeriğine döner.

VM karşılığı: infra/docker/bi/web.default.conf.template (aynı konum) ve infra/docker/bi/npm-custom-http.conf (dış kapı 0).

Test sunucusunda:  sudo python3 add-editorial-desk-upload.py
"""
import os
import re
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
s = open(P, encoding="utf-8").read()
MARK = "translation/jobs-from-file|translation/jobs/"
if MARK in s:
    print("zaten var")
    sys.exit(0)
loc_anchor = "    location /timas/api/ {\n"
if loc_anchor not in s:
    print("beklenen satır bulunamadı (genel API konumu); dokunulmadı")
    sys.exit(1)
loc = r'''    # Editoryal kitap/belge yüklemesi (ZEKI-26): eser metni, prova, belge incelemesi, çeviri kaynağı. Boyut tavanı
    # yok; köprü diske akıtır. Aynı yollardaki GET'ler de buradan geçer.
    location ~ "^/timas/api/v1/editorial/(works-from-file|works/[0-9a-f]{32}/(manuscript|proof)|documents|translation/jobs-from-file|translation/jobs/[0-9a-f]{32}/source)$" {
        set $timas_original_method $request_method;
        auth_request /_timas_session_check;
        limit_req zone=timas_api burst=30 nodelay;
        limit_req_status 429;
        rewrite ^/timas/(.*)$ /$1 break;
        include /etc/nginx/snippets/timas-semantic-caller.conf;
        proxy_pass http://127.0.0.1:8795;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Connection "";
        proxy_request_buffering off;
        proxy_read_timeout 1800s;
        proxy_send_timeout 1800s;
        client_max_body_size 0;
    }

'''
# İlk sürümün bloğu (yorum satırı + location … }) varsa kaldırılır, yenisi genel API konumunun önüne eklenir.
old = re.compile(r"    # Redaksiyon / son okuma: eser metni ve prova yükleme \(ZEKI-26\)[^\n]*\n"
                 r"    location ~ \"\^/timas/api/v1/editorial/\(works-from-file\|works/[^\n]*\n"
                 r"(?:        [^\n]*\n)+?    \}\n\n")
base, replaced = old.subn("", s, count=1)
new = base.replace(loc_anchor, loc + loc_anchor, 1)
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print(("ilk sürüm yenisiyle değiştirildi" if replaced else "eklendi") + ", nginx reload tamam")
