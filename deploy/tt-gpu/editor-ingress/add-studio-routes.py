#!/usr/bin/env python3
"""GPU genel nginx'ine Kitap Tasarım Stüdyosu'nun yollarını ekler (EDITOR bloğunun içine, idempotent).

`add-cards-routes.py` ile aynı üç kat koruma: kaynak ağ, gizli başlık, izin verilen yöntem. Stüdyo
servisi (editor-studio, 127.0.0.1:19142) yazar: iş başlatır, resim üretir, sürüm seçer, onaylar; sayfa
planında sayfa düzenler, sıralar, siler, figür/fotoğraf işler. Her yolun yöntemi ayrı ayrı sınırlıdır.
İş kimliği 14 rakam + 6 onaltılık hane; resim anahtarı sayfa numarası, «kapak» ya da planın resim kimliği
(a_ + 8 onaltılık); plan kimlikleri (sayfa, figür, fotoğraf) yalnız harf, rakam, _ ve - (en çok 64);
serbest yol parçası proxy'ye geçmez. Word yükleme yolunda gövde sınırı 25 MB; fotoğraf yüklemede
STUDIO_UPLOAD_MB + 1 MB (ortamdan, varsayılan 60 → 61 MB; köprünün yönetim ayarıyla aynı tutulmalı).

Sonradan eklenen uçlar (resume, kunye, art-mode, baskı PDF'leri; sayfa planı, süs/şekil, pazarlama kiti, seri karakter kartı 09-25) eski bloğu yerinde genişletir:
betik her koşuda eksik olanı ekler, var olana dokunmaz; değişiklik yoksa nginx'e dokunmaz.

Düzenleyen kişi köprünün `X-Editor` başlığından okunur; nginx başlığı olduğu gibi geçirir. Gizli başlık
değeri mevcut bloktan okunur, dosyaya yeni sır yazılmaz. `nginx -t` geçmezse dosya eski içeriğine döner.

GPU'da çalıştırılır:  sudo STUDIO_UPLOAD_MB=60 python3 add-studio-routes.py
"""
import os
import re
import subprocess
import sys

P = os.path.realpath("/etc/nginx/sites-enabled/kitap-eczanesi")
orig = open(P, encoding="utf-8").read()
if "EDITOR-BITTI" not in orig:
    print("EDITOR bloğu bulunamadı; önce add-cards-routes.py koşmalı")
    sys.exit(1)
UPLOAD_MB = int(os.environ.get("STUDIO_UPLOAD_MB", "60"))
gate = re.search(r'\$http_x_editor_gate != "([^"]+)"', orig).group(1)
guard = f'''        allow 85.105.0.0/16; deny all;
        if ($http_x_editor_gate != "{gate}") {{ return 403; }}'''
JOB = "[0-9]{14}[0-9a-f]{6}"
KEY = "[0-9]{1,4}|kapak|a_[0-9a-f]{8}"
ID = "[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
UP = "http://127.0.0.1:19142/v1/studio"


def loc(pattern: str, method: str, target: str, extra: str = "", timeout: int = 300) -> str:
    """`method` tek yöntem (GET) ya da seçenek listesi (PUT|DELETE)."""
    check = f"$request_method != {method}" if "|" not in method else f"$request_method !~ ^({method})$"
    return f'''    location ~ "^/editor/studio/v1/studio/{pattern}$" {{
{guard}
        if ({check}) {{ return 405; }}{extra}
        proxy_pass {UP}/{target};
        proxy_set_header Host $host;
        proxy_read_timeout {timeout}s;
    }}
'''


s = orig
changes = []

# 1) Temel stüdyo bloğu
if "# EDITOR-STUDYO " not in s:
    # Aynı yolda GET ve POST olan tek uç: /jobs (liste ve yeni iş). nginx'te yöntem başına ayrı location
    # yazılamadığı için ikisine izin veren ayrı blok.
    jobs = f'''    location = /editor/studio/v1/studio/jobs {{
{guard}
        if ($request_method !~ ^(GET|POST)$) {{ return 405; }}
        proxy_pass {UP}/jobs;
        proxy_set_header Host $host;
    }}
'''
    block = ("    # EDITOR-STUDYO  (musteri VM -> kitap tasarim studyosu; ayni uc kat koruma)\n" + jobs
             # regex location'da proxy_pass sabit URI taşıyamaz; yol parçası yakalanıp değişkenle verilir
             + loc("jobs/(docx)", "POST", "jobs/$1$is_args$args", "\n        client_max_body_size 25m;")
             + loc(f"jobs/({JOB})", "GET", "jobs/$1")
             + loc(f"jobs/({JOB})/(restart|resume|kunye|art-mode)", "POST", "jobs/$1/$2")
             + loc(f"jobs/({JOB})/pages/([0-9]{{1,4}})/preview", "GET", "jobs/$1/pages/$2/preview$is_args$args")
             + loc(f"jobs/({JOB})/cover/preview", "GET", "jobs/$1/cover/preview$is_args$args")
             + loc(f"jobs/({JOB})/art/({KEY})/([0-9]{{1,3}})", "GET", "jobs/$1/art/$2/$3$is_args$args")
             + loc(f"jobs/({JOB})/art/({KEY})/(regenerate|select|approve)", "POST", "jobs/$1/art/$2/$3")
             + loc(f"jobs/({JOB})/characters/([0-9]{{1,2}})", "GET", "jobs/$1/characters/$2$is_args$args")
             + loc(f"jobs/({JOB})/pdf/(ic|kapak|baski-ic|baski-kapak)", "GET", "jobs/$1/pdf/$2"))
    s = s.replace("    # EDITOR-BITTI", block + "    # EDITOR-BITTI", 1)
    changes.append("temel stüdyo yolları")
else:
    # Eski bloğun yerinde genişletilmesi (09-24/25 uçları; sayfa planının resim kimliği a_…).
    J = "jobs/([0-9]{14}[0-9a-f]{6})/"
    before = s
    for old in (J + 'restart$"', J + '(restart|resume)$"', J + '(restart|resume|kunye)$"'):
        s = s.replace(old, J + '(restart|resume|kunye|art-mode)$"')
    # Word yüklemesinde resim seçimi sorgu parametresiyle gider (art_mode); eski blok sorguyu düşürüyordu.
    s = re.sub(r'(location ~ "\^/editor/studio/v1/studio/jobs/\(docx\)\$" \{(?:(?!location)[\s\S])*?proxy_pass http://127\.0\.0\.1:19142/v1/studio/jobs/\$1);',
               r"\1$is_args$args;", s, count=1)
    s = s.replace(J + '(pdf)/(ic|kapak)$"', J + 'pdf/(ic|kapak|baski-ic|baski-kapak)$"')
    s = s.replace(J + 'pdf/(ic|kapak)$"', J + 'pdf/(ic|kapak|baski-ic|baski-kapak)$"')
    s = s.replace("proxy_pass http://127.0.0.1:19142/v1/studio/jobs/$1/restart;",
                  "proxy_pass http://127.0.0.1:19142/v1/studio/jobs/$1/$2;")
    s = s.replace(J + "art/([0-9]{1,4}|kapak)/", J + f"art/({KEY})/")
    if s != before:
        changes.append("eski stüdyo yolları güncellendi (kunye, art-mode, Word sorgusu, baskı PDF'leri, a_ resim kimliği)")

# 2) Sayfa planı bloğu
P_ = f"jobs/({JOB})/plan"
body_mb = UPLOAD_MB + 1
if "EDITOR-STUDYO-PLAN" not in s:
    plan = ("    # EDITOR-STUDYO-PLAN  (sayfa plani: docs/analiz/studyo-sayfa-plani-sozlesme.md)\n"
            + loc(P_, "GET", "jobs/$1/plan", timeout=60)
            + loc(f"{P_}/(freeze|order|restore|figures)", "POST", "jobs/$1/plan/$2")
            + loc(f"{P_}/(unused-art|history|jobs)", "GET", "jobs/$1/plan/$2", timeout=60)
            + loc(f"{P_}/palette", "PUT", "jobs/$1/plan/palette")
            + loc(f"{P_}/pages", "POST", "jobs/$1/plan/pages")
            + loc(f"{P_}/pages/({ID})", "PUT|DELETE", "jobs/$1/plan/pages/$2$is_args$args")
            + loc(f"{P_}/pages/({ID})/split", "POST", "jobs/$1/plan/pages/$2/split")
            + loc(f"{P_}/pages/({ID})/bubbles/suggest", "POST", "jobs/$1/plan/pages/$2/bubbles/suggest")
            + loc(f"{P_}/pages/({ID})/preview", "GET", "jobs/$1/plan/pages/$2/preview$is_args$args")
            + loc(f"{P_}/assets/({ID})", "GET|DELETE", "jobs/$1/plan/assets/$2$is_args$args")
            + loc(f"{P_}/assets/({ID})/(cutout|upscale)", "POST", "jobs/$1/plan/assets/$2/$3")
            + loc(f"{P_}/photos", "PUT", "jobs/$1/plan/photos$is_args$args",
                  f"\n        client_max_body_size {body_mb}m;  # STUDIO_UPLOAD_MB+1", timeout=600))
    s = s.replace("    # EDITOR-BITTI", plan + "    # EDITOR-BITTI", 1)
    changes.append(f"sayfa planı yolları (fotoğraf gövdesi {body_mb} MB)")
else:
    fixed = re.sub(r"client_max_body_size \d+m;  # STUDIO_UPLOAD_MB\+1", f"client_max_body_size {body_mb}m;  # STUDIO_UPLOAD_MB+1", s)
    if fixed != s:
        s = fixed
        changes.append(f"fotoğraf gövde sınırı {body_mb} MB")

# 3) Süs/şekil kataloğu ve efekt önizlemeleri (yalnız okuma; yazan uç yok, şekil sayfa PUT'uyla kaydedilir)
KIND = "[a-z][a-z0-9_-]{0,31}"                      # köprünün NAME kalıbıyla aynı (rakam da olabilir)
if "EDITOR-STUDYO-OGE" not in s:
    oge = ("    # EDITOR-STUDYO-OGE  (sus/sekil katalogu ve efekt yazi onizlemeleri)\n"
           + loc(f"{P_}/elements/catalog", "GET", "jobs/$1/plan/elements/catalog", timeout=60)
           + loc(f"{P_}/elements/({KIND})/preview", "GET", "jobs/$1/plan/elements/$2/preview$is_args$args", timeout=60)
           + loc(f"{P_}/effects/({KIND})/preview", "GET", "jobs/$1/plan/effects/$2/preview$is_args$args", timeout=60))
    s = s.replace("    # EDITOR-BITTI", oge + "    # EDITOR-BITTI", 1)
    changes.append("süs/şekil ve efekt önizleme yolları")
else:
    # 09-25 ilk sürümü tür/stil adında rakama izin vermiyordu; yerinde genişletilir.
    widened = s.replace("/elements/([a-z][a-z_-]{0,31})/preview", f"/elements/({KIND})/preview").replace(
        "/effects/([a-z][a-z_-]{0,31})/preview", f"/effects/({KIND})/preview")
    if widened != s:
        s = widened
        changes.append("süs/şekil yollarında tür adı kalıbı genişletildi")

# 4) Pazarlama kiti (arka kapak yazısı, ürün sayfası, sosyal medya görselleri, öğretmen kılavuzu; api_marketing.py)
if "EDITOR-STUDYO-PAZARLAMA" not in s:
    M = f"jobs/({JOB})/marketing"
    SID = "s_[0-9a-f]{8}"
    pazarlama = ("    # EDITOR-STUDYO-PAZARLAMA  (pazarlama kiti: arka kapak, urun sayfasi, sosyal medya, kilavuz)\n"
                 + loc(M, "GET", "jobs/$1/marketing", timeout=60)
                 + loc(f"{M}/(back-cover|product|guide)/generate", "POST", "jobs/$1/marketing/$2/generate", timeout=60)
                 + loc(f"{M}/(back-cover|product|guide)", "PUT", "jobs/$1/marketing/$2")
                 + loc(f"{M}/(back-cover|product|guide)/approve", "POST", "jobs/$1/marketing/$2/approve")
                 + loc(f"{M}/back-cover/(apply|revert)", "POST", "jobs/$1/marketing/back-cover/$2")
                 + loc(f"{M}/product/seo", "POST", "jobs/$1/marketing/product/seo", timeout=60)
                 + loc(f"{M}/product/export", "GET", "jobs/$1/marketing/product/export$is_args$args", timeout=60)
                 + loc(f"{M}/guide/pdf", "GET", "jobs/$1/marketing/guide/pdf")
                 + loc(f"{M}/social", "POST", "jobs/$1/marketing/social", timeout=180)
                 + loc(f"{M}/social/zip", "GET", "jobs/$1/marketing/social/zip")
                 + loc(f"{M}/social/sources/({KEY}|{ID})", "GET", "jobs/$1/marketing/social/sources/$2$is_args$args",
                       timeout=60)
                 + loc(f"{M}/social/({SID})", "GET|DELETE", "jobs/$1/marketing/social/$2$is_args$args", timeout=60)
                 + loc(f"{M}/social/({SID})/approve", "POST", "jobs/$1/marketing/social/$2/approve", timeout=60))
    s = s.replace("    # EDITOR-BITTI", pazarlama + "    # EDITOR-BITTI", 1)
    changes.append("pazarlama kiti yolları")

# 4) Seri karakter kartı (apps/editor/src/editor/production/api_characters.py); kart ve referans kimlikleri biçimle sınırlı
if "EDITOR-STUDYO-KARAKTER" not in s:
    K = f"jobs/({JOB})/character-cards"
    CID = "c_[0-9a-f]{8}"
    RID = "r_[0-9a-f]{8}"
    kart = ("    # EDITOR-STUDYO-KARAKTER  (seri karakter karti)\n"
            + loc(K, "GET", "jobs/$1/character-cards", timeout=60)
            + loc(f"{K}/series", "PUT", "jobs/$1/character-cards/series", timeout=60)
            + loc(f"{K}/(suggest|check|cards)", "POST", "jobs/$1/character-cards/$2", timeout=60)
            + loc(f"{K}/(history)", "GET", "jobs/$1/character-cards/$2", timeout=60)
            + loc(f"{K}/cards/({CID})", "PUT|DELETE", "jobs/$1/character-cards/cards/$2$is_args$args", timeout=60)
            + loc(f"{K}/cards/({CID})/(approve|translate|palette)", "POST", "jobs/$1/character-cards/cards/$2/$3")
            + loc(f"{K}/cards/({CID})/refs", "PUT|POST", "jobs/$1/character-cards/cards/$2/refs$is_args$args",
                  f"\n        client_max_body_size {body_mb}m;  # STUDIO_UPLOAD_MB+1", timeout=600)
            + loc(f"{K}/cards/({CID})/refs/({RID})", "GET|DELETE",
                  "jobs/$1/character-cards/cards/$2/refs/$3$is_args$args", timeout=60)
            + loc(f"{K}/cards/({CID})/refs/({RID})/primary", "POST",
                  "jobs/$1/character-cards/cards/$2/refs/$3/primary", timeout=60)
            + loc("character-settings", "GET|PUT", "character-settings", timeout=30))
    s = s.replace("    # EDITOR-BITTI", kart + "    # EDITOR-BITTI", 1)
    changes.append("seri karakter kartı yolları")

if s == orig:
    print("zaten var (güncel)")
    sys.exit(0)
open(P, "w", encoding="utf-8").write(s)
t = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
if t.returncode != 0:
    open(P, "w", encoding="utf-8").write(orig)
    print("nginx -t DÜŞTÜ, dosya eski hâline döndü:\n", t.stderr)
    sys.exit(1)
subprocess.run(["systemctl", "reload", "nginx"], check=True)
print("güncellendi:", "; ".join(changes), "— nginx reload tamam")
