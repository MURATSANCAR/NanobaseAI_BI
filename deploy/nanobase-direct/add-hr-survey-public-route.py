#!/usr/bin/env python3
"""Portal nginx'ine M58 oturumsuz anket formu konumunu ekler (idempotent; add-marketing-creative-routes.py kalıbı).

**Kullanıcı onayı ister:** portal girişi yalnız AD ile (bellek: no-demo-login); bu konum tek istisnadır ve yalnız
`/timas/api/v1/hr/survey-public/<jeton|kod>` yolunu `auth_request` dışında tutar. Uç kendi jetonunu/kodunu doğrular, kişi
yazmaz; başka hiçbir yol açılmaz. Onay gelene kadar koşturulmaz; onaysız ortamda form yalnız portal oturumuyla açılır
(bilgisayarsız çalışanın basılı kodu çalışmaz).

Kaba kuvvete karşı ayrı, sıkı bir istek sınırı (dakikada 20, patlama 10) ve yalnız GET/POST. Gövde 64 KB.
Müşteri VM'inde aynı konum `infra/docker/bi/web.default.conf.template`'e onaydan sonra eklenir.
`nginx -t` geçmezse dosya eski içeriğine döner.

Test sunucusunda (onaydan sonra):  sudo python3 add-hr-survey-public-route.py
"""
import os
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/portal.nanobase.ai")
s = open(P, encoding="utf-8").read()
if "hr/survey-public" in s:
    print("zaten var")
    sys.exit(0)
loc_anchor = "    location /timas/api/ {\n"
zone_anchor = "limit_req_zone"
if loc_anchor not in s or zone_anchor not in s:
    print("beklenen satırlar bulunamadı (genel API konumu ya da istek sınırı bölgesi); dokunulmadı")
    sys.exit(1)
zone = "limit_req_zone $binary_remote_addr zone=timas_survey_public:1m rate=20r/m;\n"
loc = r'''    # M58 oturumsuz anket formu (kullanıcı onayıyla): yalnız jeton/kod yolu, AD girişi dışında. Uç kendi jetonunu doğrular.
    location ~ "^/timas/api/v1/hr/survey-public/[A-Za-z0-9_-]{8,64}$" {
        if ($request_method !~ ^(GET|POST)$) { return 405; }
        limit_req zone=timas_survey_public burst=10 nodelay;
        limit_req_status 429;
        client_max_body_size 64k;
        rewrite ^/timas/(.*)$ /$1 break;
        include /etc/nginx/snippets/timas-semantic-caller.conf;
        proxy_pass http://127.0.0.1:8795;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Connection "";
        # Cevap kişiye bağlanmasın: istemci adresi köprüye iletilmez.
        proxy_set_header X-Real-IP "";
        proxy_set_header X-Forwarded-For "";
        access_log off;
        proxy_read_timeout 60s;
    }

'''
first_zone = s.index(zone_anchor)
new = s[:first_zone] + zone + s[first_zone:]
new = new.replace(loc_anchor, loc + loc_anchor, 1)
open(P, "w", encoding="utf-8").write(new)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(s)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("eklendi, nginx reload tamam")
