"""M37 Okur topluluğu — gerçek API ↔ doğrudan SQL kabulü (test sunucusunda, yan port köprüsü, salt okunur CRM).

Uçların kullanıcıya verdiği sonuç köprü kodu kullanılmadan yazılmış doğrudan CRM sorgularıyla karşılaştırılır
(`referans.sql` R1–R8). Okur sayıları (R1–R5) H2 okur veri tabanından gelir; H2 bu köprüde bağlı değilse o denetimler
«DOĞRULANAMADI» yazılır (başarı sayılmaz). Her koşuda bütün `okur` GET cevaplarında e-posta/telefon kalıbı ve kişi
kolonu aranır (kabul 8).

Yazma: H2 bağlıysa bir deneme segmenti, her durumda bir deneme programı açılır (adları «KABUL TESTİ» ile başlar);
kimlikler `--out` dosyasına yazılır, `temizlik.py` siler (değişiklik kaydı dahil). Yorum durumu yazılmaz.

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin 15 dk'lık oturum çerezi), SEMANTIC_CRM_CONNECTION_FILE,
PYTHONPATH=<aday ağaç>/backend, SEMANTIC_STORE_DSN (R8 için). İsteğe bağlı: M37_YIL (etkinlik yılı; varsayılan ekranın
seçtiği son yıl), M37_CELISKI_TUR (R3'ün izin sağlığındaki tür anahtarı; varsayılan izinsiz_gonderim), M37_KURAL_JSON
(deneme segmentinin kuralı; varsayılan ilk «çağrışım yok» ilgi alanı), M37_R5_SQL (R5 referansı; {ilgi_id} yer tutucusu).
Kullanım: python kabul.py --out /tmp/claude-<oturum>/m37-kimlikler.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

from semantic_bridge import budget_sources as bsrc

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
P = BASE + "/api/v1/okur"
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
results: list[tuple[str, str, str]] = []   # (ad, GEÇTİ|KALDI|DOĞRULANAMADI, ayrıntı)
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?90[\s\-.]?|0)?\(?5\d{2}\)?[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}(?!\d)")
PERSONAL = re.compile(r'"(fullname|emailaddress\d|mobilephone|telephone\d|address1_[a-z_]+)"\s*:', re.I)


def http(method: str, url: str, body=None, timeout=900):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Cookie": COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            return r.status, json.loads(payload) if payload[:1] in (b"{", b"[") else payload
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, payload


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, "GEÇTİ" if ok else "KALDI", detail))
    print(("GEÇTİ " if ok else "KALDI ") + name + (f" — {detail}" if detail else ""), flush=True)
    _progress()


def unverified(name: str, why: str) -> None:
    results.append((name, "DOĞRULANAMADI", why))
    print(f"DOĞRULANAMADI {name} — {why}", flush=True)
    _progress()


def _progress() -> None:
    if len(results) % 10 == 0:
        c = {k: sum(1 for r in results if r[1] == k) for k in ("GEÇTİ", "KALDI", "DOĞRULANAMADI")}
        print(f"-- ara durum: {c['GEÇTİ']} geçti, {c['KALDI']} kaldı, {c['DOĞRULANAMADI']} doğrulanamadı", flush=True)


def clean(name: str, payload) -> None:
    text = json.dumps(payload, ensure_ascii=False)
    hits = [m.group(0) for rx in (EMAIL, PHONE, PERSONAL) for m in rx.finditer(text)][:5]
    tech = [w for w in ("qwen", "vllm", "timesfm", "openai") if w in text.lower()]
    check(f"kişi verisi ve teknoloji adı yok: {name}", not hits and not tech, f"{hits} {tech}".strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    created: dict[str, list[str]] = {"segments": [], "programs": []}

    s, meta = http("GET", P + "/meta")
    check("meta 200", s == 200, str(s))
    if s != 200:
        return finish(a.out, created)
    bagli = meta["cekirdek"]["bagli"]
    print(f"   okur çekirdeği (H2): {'bağlı' if bagli else 'bağlı değil'}; model: {meta['modelVar']}")
    s, _ = http("POST", P + "/segments", {})
    check("boş gövdeyle segment 400", s == 400, str(s))
    s, _ = http("GET", P + "/segments/yok-boyle")
    check("olmayan segment 404", s == 404, str(s))
    s, ov = http("GET", P + "/overview")
    check("overview 200", s == 200, str(s))
    clean("overview", ov)

    # R1–R4 · okur envanteri ve izin sağlığı (H2 üzerinden).
    if not bagli or not ov.get("envanter", {}).get("bagli"):
        for n in ("R1 kayıt tipi dağılımı", "R2 izin oranları", "R3 izin çelişkisi", "R4 aday kaynakları", "R5 segment önizlemesi"):
            unverified(n, "okur çekirdeği (H2) bu köprüde bağlı değil")
    else:
        rows = ov["envanter"]["satirlar"]
        ref1 = {str(r["kayit_tipi"] if r["kayit_tipi"] is not None else ""): int(r["sayi"]) for r in crm(
            f"SELECT CAST(new_kayittipi AS nvarchar(20)) AS kayit_tipi, COUNT(*) AS sayi FROM {SCHEMA}.ContactBase WHERE statecode = 0 GROUP BY new_kayittipi")}
        kisi = [r for r in rows if "kişi" in r["kaynak"].lower() or "contact" in r["kaynak"].lower()]
        print(f"   R1 SQL {ref1} · ekran (CRM kişi) {[(r['kayitTipi'], r['toplam']) for r in kisi]}")
        check("R1 CRM kişi toplamı SQL'i aşmaz ve boş değil", 0 < sum(r["toplam"] for r in kisi) <= sum(ref1.values()),
              f"ekran {sum(r['toplam'] for r in kisi)} / SQL {sum(ref1.values())}")
        r2 = crm(f"SELECT COUNT(*) AS toplam, SUM(CASE WHEN new_kvkkonayi = 1 THEN 1 ELSE 0 END) AS kvkk, "
                 f"SUM(CASE WHEN new_iysonayi = 1 THEN 1 ELSE 0 END) AS iys FROM {SCHEMA}.ContactBase WHERE statecode = 0")[0]
        sk = sum(r["kvkkOnayli"] or 0 for r in kisi)
        si = sum(r["iysOnayli"] or 0 for r in kisi)
        same = sum(r["toplam"] for r in kisi) == int(r2["toplam"])
        if same:
            check("R2 KVKK ve İYS onay sayısı birebir", sk == int(r2["kvkk"] or 0) and si == int(r2["iys"] or 0),
                  f"ekran {sk}/{si} · SQL {r2['kvkk']}/{r2['iys']}")
        else:
            check("R2 onay sayısı SQL'i aşmaz (H2 okur ayrımı uygulanmış)", sk <= int(r2["kvkk"] or 0) and si <= int(r2["iys"] or 0),
                  f"ekran {sk}/{si} · SQL {r2['kvkk']}/{r2['iys']}")
        s, ch = http("GET", P + "/consent-health")
        clean("consent-health", ch)
        tur = os.environ.get("M37_CELISKI_TUR", "izinsiz_gonderim")
        got = next((x["sayi"] for x in ch.get("items", []) if x["tur"] == tur), None)
        r3 = int(crm(f"SELECT COUNT(DISTINCT g.obs_kisiid) AS n FROM {SCHEMA}.obs_kampanyagonderimleriBase g "
                     f"JOIN {SCHEMA}.ContactBase c ON c.ContactId = g.obs_kisiid WHERE ISNULL(c.new_iysonayi, 0) = 0")[0]["n"] or 0)
        if got is None:
            unverified("R3 izin çelişkisi", f"izin sağlığında «{tur}» türü yok; türler {[x['tur'] for x in ch.get('items', [])]} (SQL {r3})")
        else:
            check("R3 «İYS yok ama gönderim var» birebir", got == r3, f"ekran {got} / SQL {r3}")
        r4 = crm(f"SELECT COUNT(*) AS n FROM {SCHEMA}.LeadBase")[0]["n"]
        aday = [r for r in rows if "aday" in r["kaynak"].lower() or "lead" in r["kaynak"].lower()]
        check("R4 aday toplamı SQL'i aşmaz ve boş değil", 0 < sum(r["toplam"] for r in aday) <= int(r4), f"ekran {sum(r['toplam'] for r in aday)} / SQL {r4}")

        # R5 · deneme segmenti ve önizleme.
        s, cats = http("GET", P + "/categories")
        usable = [c for c in cats.get("items", []) if c.get("kullanilabilir")]
        rule = json.loads(os.environ["M37_KURAL_JSON"]) if os.environ.get("M37_KURAL_JSON") else (
            {"ilgi_alanlari": [usable[0]["id"]]} if usable else None)
        if not rule:
            unverified("R5 segment önizlemesi", "«çağrışım yok» işaretli ilgi alanı yok (önce KVKK kararı) ve M37_KURAL_JSON verilmedi")
        else:
            s, seg = http("POST", P + "/segments", {"ad": "KABUL TESTİ — silinecek", "kural": rule, "kanal": "eposta",
                                                   "amac": "M37 kabul testi, gönderim yok, silinecek",
                                                   "sureBitis": (date.today() + timedelta(days=7)).isoformat()})
            check("deneme segmenti açıldı", s == 201, str(s))
            if s == 201:
                created["segments"].append(seg["id"])
                s, m = http("POST", P + f"/segments/{seg['id']}/preview", timeout=1800)
                check("segment ölçüldü", s == 200 and m.get("sonOlcum"), str(s))
                ilgi = (rule.get("ilgi_alanlari") or [None])[0]
                sql = os.environ.get("M37_R5_SQL") or (
                    f"SELECT COUNT(DISTINCT c.ContactId) AS toplam FROM {SCHEMA}.new_contact_new_kitapilgialanBase b "
                    f"JOIN {SCHEMA}.ContactBase c ON c.ContactId = b.contactid WHERE c.statecode = 0 AND b.new_kitapilgialanid = '{{ilgi_id}}'")
                try:
                    ref = int(crm(sql.replace("{ilgi_id}", str(ilgi)))[0]["toplam"] or 0)
                    got = (m.get("sonOlcum") or {}).get("toplam")
                    check("R5 segment toplamı ≤ elle yazılmış SQL (H2 okur ayrımıyla eşit ya da küçük)", got is not None and got <= ref,
                          f"ekran {got} / SQL {ref}")
                except bsrc.SourceError as e:
                    unverified("R5 segment önizlemesi", f"referans SQL koşmadı ({e}); N:N kolon adları ölçülecek")
                clean("segment", m)

    # R6–R7 · CRM geçmiş etkinlikler (M37'nin kendi kaynağı).
    yil = int(os.environ.get("M37_YIL") or 0)
    s, ev = http("GET", P + f"/events-summary{'?yil=' + str(yil) if yil else ''}", timeout=1800)
    check("events-summary 200", s == 200, str(s) if s != 200 else f"{ev['yil']}: {ev['toplam']} etkinlik")
    if s == 200:
        y = ev["yil"]
        cond = (f"new_ziyarettipi IS NULL AND new_BalangTarihi >= '{y}-01-01' AND new_BalangTarihi < '{y + 1}-01-01'"
                if ev["ziyaretHaric"] else f"new_BalangTarihi >= '{y}-01-01' AND new_BalangTarihi < '{y + 1}-01-01'")
        if ev["tipSuzgeci"]:
            unverified("R6 etkinlik özeti", f"OKUR_ETKINLIK_TIPLERI süzgeci açık ({ev['tipSuzgeci']}); referans tipsiz yazıldı")
        else:
            r6 = crm(f"SELECT COUNT(*) AS n, SUM(new_katilimcisayisi) AS k, SUM(new_SatilanKitapAd) AS s FROM {SCHEMA}.new_etkinlikBase "
                     f"WHERE statuscode = 100000002 AND {cond}")[0]
            check("R6 tamamlanan etkinlik, katılımcı, satılan birebir",
                  (ev["tamamlanan"], ev["katilimci"], ev["satilan"]) == (int(r6["n"] or 0), int(r6["k"] or 0), int(r6["s"] or 0)),
                  f"ekran {(ev['tamamlanan'], ev['katilimci'], ev['satilan'])} / SQL {(r6['n'], r6['k'], r6['s'])}")
            r6b = sum(int(r["n"]) for r in crm(f"SELECT COUNT(*) AS n FROM {SCHEMA}.new_etkinlikBase WHERE {cond}"))
            check("R6b yılın bütün etkinlikleri birebir", ev["toplam"] == r6b, f"ekran {ev['toplam']} / SQL {r6b}")
            r7 = {str(r["tip"]): int(r["n"]) for r in crm(
                f"SELECT ISNULL(t.new_name, '(tipsiz)') AS tip, COUNT(*) AS n FROM {SCHEMA}.new_etkinlikBase e "
                f"LEFT JOIN {SCHEMA}.new_etkinliktipiBase t ON t.new_etkinliktipiId = e.new_etkinliktipiid "
                f"WHERE e.statuscode = 100000002 AND {cond.replace('new_', 'e.new_')} GROUP BY t.new_name")}
            screen = {g["ad"]: g["etkinlik"] for g in ev["tipler"]}
            check("R7 tipe göre tamamlanan birebir", screen == r7, f"fark {set(screen.items()) ^ set(r7.items())}")
        clean("events-summary", ev)

    # R8 · yorumlar.
    s, rv = http("GET", P + "/reviews", timeout=900)
    if s == 200:
        seo = rv.get("seo")
        n = rv["sayilar"]["toplam"]
        if seo:
            check("R8 yorum toplamı SEO gece özetiyle tutarlı (anlık ≥ gece)", n >= seo["yorum"], f"ekran {n} / SEO {seo['yorum']} ({seo['urun']} ürün)")
        else:
            unverified("R8 yorumlar", "SEO yorum özeti yok (gece okuması koşmamış)")
        check("yorum durumları toplamı tutarlı", sum(rv["sayilar"][k] for k in ("cevapsiz", "taslak", "cevaplandi")) == n, json.dumps(rv["sayilar"]))
        clean("reviews", rv)
    else:
        unverified("R8 yorumlar", f"yorum ucu {s}: {str(rv)[:200]}")

    # Program: yazma ve geri okuma (deneme).
    s, p = http("POST", P + "/programs", {"tur": "okuma_kulubu", "ad": "KABUL TESTİ — silinecek",
                                          "tarih": (date.today() + timedelta(days=3)).isoformat()})
    check("deneme programı açıldı", s == 201, str(s))
    if s == 201:
        created["programs"].append(p["id"])
        s, lst = http("GET", P + "/programs")
        check("program takvimde", s == 200 and any(x["id"] == p["id"] for x in lst["items"]), str(s))
        clean("programs", lst)
    for path in ("/segments", "/categories", "/inventory", "/contract/segments"):
        s, body = http("GET", P + path)
        check(f"GET {path} 200", s == 200, str(s))
        clean(path, body)
    return finish(a.out, created)


def finish(out_path: str, created: dict[str, list[str]]) -> int:
    with open(out_path, "w") as fh:
        json.dump(created, fh)
    c = {k: sum(1 for r in results if r[1] == k) for k in ("GEÇTİ", "KALDI", "DOĞRULANAMADI")}
    print(f"== SONUÇ: {c['GEÇTİ']} geçti, {c['KALDI']} kaldı, {c['DOĞRULANAMADI']} doğrulanamadı; kimlikler {out_path} (temizlik.py ile silin)")
    return 0 if not c["KALDI"] else 1


if __name__ == "__main__":
    sys.exit(main())
