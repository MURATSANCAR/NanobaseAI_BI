#!/usr/bin/env python3
"""M34 E-ticaret — test sunucusunda gerçek API ↔ doğrudan SQL kabulü (yerelde koşulmaz).

Ekranın kullandığı uçların verdiği sonuç, köprü kodu kullanılmadan yazılmış doğrudan CRM (.28), Logo (.25) ve meta
Postgres sorgularıyla karşılaştırılır (`referans.sql` R1–R8). Uygulamanın SQL'i yeniden koşturulmaz. Örnekler her koşuda
rastgele seçilir (sabit kitap yok). Her kontrol: OK / FARK / DOĞRULANAMADI / ÖLÇÜM; her 10 kontrolde ara durum yazılır.

Önce (bir kez, elle; süresi günlüğe):
    curl -X POST -H "X-Semantic-Caller: $SEMANTIC_CALLER_TOKEN" 'http://127.0.0.1:8795/api/v1/eticaret/run-due?model=false&weekly=false'

Koşturma (köprünün sanal ortamı ve env dosyası; timasai'nin 15 dk'lık oturum çerezi — bellek: test-login-as-timasai):
    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <aday ağaç>/backend && BRIDGE_URL=http://127.0.0.1:8798 TIMAS_COOKIE='timas_session=…' \\
      python3 ../scripts/acceptance/M34/kabul.py --out /tmp/claude-<oturum>/m34-kabul.json [--yazma --ids /tmp/claude-<oturum>/m34-ids.json]

`--yazma`: bir açık farkı «sonra» işaretleyip geri «açık» yapar (işaret akışı, 422 gerekçesiz bilinçli); dokunulan farkın önceki
hâli ve kimliği `--ids` dosyasına yazılır, `temizlik.py` farkı eski hâline döndürür ve günlük/değişiklik kaydı satırlarını siler.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BASE = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795").rstrip("/") + "/api/v1/eticaret"
COOKIE = os.environ.get("TIMAS_COOKIE", "")
GONE = ("bizim_degil", "devredildi", "geri_istendi", "iptal", "cekildi")
results: list[dict] = []


def record(name: str, status: str, **detail) -> None:
    results.append({"kontrol": name, "durum": status, **detail})
    print(f"{status:14} {name} — {json.dumps(detail, ensure_ascii=False, default=str)[:400]}", flush=True)
    if len(results) % 10 == 0:
        c = {s: sum(1 for r in results if r["durum"] == s) for s in ("OK", "FARK", "DOĞRULANAMADI", "ÖLÇÜM")}
        print(f"-- ara durum: {c}", flush=True)


def http(method: str, path: str, body=None, timeout=900):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Cookie": COOKIE, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def q(v: str) -> str:
    return str(v).replace("'", "''")


def digits(v) -> str:
    return re.sub(r"[^0-9]", "", str(v or ""))


def all_diffs(params: dict) -> list[dict]:
    out, page = [], 0
    while True:
        s, d = http("GET", "/diffs?" + urllib.parse.urlencode({**params, "page": page}))
        if s != 200:
            raise RuntimeError(f"/diffs {s} {d}")
        out += d["items"]
        if len(out) >= d["total"] or not d["items"]:
            return out
        page += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m34-kabul.json")
    ap.add_argument("--yazma", action="store_true")
    ap.add_argument("--ids", default="m34-ids.json")
    a = ap.parse_args()
    if not COOKIE:
        print("TIMAS_COOKIE gerekli (timasai'nin kısa oturumu).")
        return 2
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    schema = admin_mod.conf("CRM_SCHEMA", "Timas_MSCRM.dbo") or "Timas_MSCRM.dbo"
    p = schema.rstrip(".") + "."
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    firms = bsrc.firms_by_year(logo)
    cur = firms[max(firms)]

    s, ov = http("GET", "/overview")
    if s != 200 or not ov.get("sonOkuma"):
        record("okuma yapılmış", "DOĞRULANAMADI", durum=s, not_="önce run-due elle koşturulmalı")
        return finish(a)
    record("okuma yapılmış", "OK" if not ov["sonOkuma"].get("hata") else "FARK", son=ov["sonOkuma"].get("bitti"),
           hata=ov["sonOkuma"].get("hata"), kaynaklar=ov["sonOkuma"]["ozet"].get("kaynaklar"))
    s, meta = http("GET", "/meta")
    record("meta: gönderim kapalı", "OK" if s == 200 and meta.get("gonderim") is False else "FARK", durum=s)

    # 0 · Geçersiz istekler (yazmadan önce).
    s, _ = http("GET", "/diffs?tur=uydurma")
    record("bilinmeyen tür 422", "OK" if s == 422 else "FARK", durum=s)
    s, _ = http("GET", "/items/yok-boyle-kitap")
    record("olmayan kitap 404", "OK" if s == 404 else "FARK", durum=s)
    s, _ = http("GET", "/export/content-pack?keys=")
    record("boş içerik paketi 400 (ya da yetkisiz 403)", "OK" if s in (400, 403) else "FARK", durum=s)

    # R1 · CRM'de «TSOFT Aktif».
    r = crm(f"SELECT COUNT(*) AS kart, COUNT(DISTINCT new_ean13) AS ean, SUM(CASE WHEN new_ean13 IS NULL THEN 1 ELSE 0 END) AS eansiz "
            f"FROM {p}new_kitapBase WHERE new_tsoftaktif = 1")[0]
    expected = int(r["ean"] or 0) + int(r["eansiz"] or 0)
    got = ov["gostergeler"]["crmTsoftAktif"]
    record("R1 CRM TSOFT Aktif", "OK" if got == expected else "FARK", ekran=got, referans_ean_eansiz=expected, referans_kart=r["kart"],
           not_="aynı EAN'lı iki kart ekranda bir kitaptır; kart sayısı ile fark ÖLÇÜM")

    # R2 · «CRM'de aktif, sitede yok».
    crm_set = {digits(x["ean"]) for x in crm(f"SELECT new_ean13 AS ean FROM {p}new_kitapBase WHERE new_tsoftaktif = 1 AND statecode = 0 "
                                             f"AND new_ean13 IS NOT NULL") if digits(x["ean"])}
    with engine.connect() as c:
        site = {digits(x[0]) for x in c.execute(sa.text(
            "SELECT data_json::json->>'Barcode' FROM semantic_seo_products WHERE tenant_id = :t AND active"), {"t": tenant}).all()}
    ref = crm_set - site
    diffs = all_diffs({"tur": "aktiflik", "durum": "acik-hepsi"})
    app = {d["productKey"] for d in diffs if d["crm"] == "TSOFT Aktif"}
    record("R2 CRM'de aktif, sitede yok (sayı)", "OK" if app == ref else "FARK", ekran=len(app), referans=len(ref),
           yalniz_ekranda=sorted(app - ref)[:20], yalniz_referansta=sorted(ref - app)[:20],
           not_="bilinçli/düzeltildi işaretli fark da sayılır (acik-hepsi); aynı EAN'lı pasif ikinci kart farkı ÖLÇÜM")
    top = sorted(ref)[:20]
    record("R2 ilk 20 barkod birebir", "OK" if all(k in app for k in top) else "FARK", ornek=top)

    # R3 · Pazar yeri sell-in.
    s, mk = http("GET", "/marketplaces?yenile=true", timeout=1800)
    if s != 200:
        record("R3 pazar yeri ucu", "DOĞRULANAMADI", durum=s, cevap=str(mk)[:300])
    else:
        yil, son = mk["yil"], date.fromisoformat(mk["donem"]["son"])
        f = firms[yil]
        chans = ", ".join(f"N'{q(x)}'" for x in mk["kanallar"])
        ref3 = {x["kod"].strip(): float(x["net"] or 0) for x in logo(
            f"SELECT C.CODE AS kod, SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net "
            f"FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF "
            f"WHERE C.SPECODE2 IN ({chans}) AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9) "
            f"AND S.DATE_ >= '{yil}-01-01' AND S.DATE_ < '{(son + timedelta(days=1)).isoformat()}' GROUP BY C.CODE")}
        app3 = {x["kod"]: x["net"] for x in mk["cariler"]}
        bad = {k: (app3.get(k), v) for k, v in ref3.items() if abs((app3.get(k) or 0) - v) >= 0.005}
        bad |= {k: (v, None) for k, v in app3.items() if k not in ref3}
        record("R3 cari başına net ciro (kuruş)", "OK" if not bad else "FARK", cari=len(ref3), toplam_ekran=mk["toplam"]["net"],
               toplam_referans=round(sum(ref3.values()), 2), farklar=dict(list(bad.items())[:10]))
        inv = {x["kod"].strip(): float(x["net"] or 0) for x in logo(
            f"SELECT C.CODE AS kod, SUM(CASE WHEN I.TRCODE IN (7,8,9) THEN I.NETTOTAL ELSE -I.NETTOTAL END) AS net "
            f"FROM dbo.LG_{f}_01_INVOICE I JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = I.CLIENTREF "
            f"WHERE I.CANCELLED = 0 AND I.TRCODE IN (2,3,7,8,9) AND C.SPECODE2 IN ({chans}) "
            f"AND I.DATE_ >= '{yil}-01-01' AND I.DATE_ < '{(son + timedelta(days=1)).isoformat()}' GROUP BY C.CODE")}
        record("R3-Ö fatura başlığı (NETTOTAL) ile satır (LINENET) farkı", "ÖLÇÜM",
               satir=round(sum(ref3.values()), 2), baslik=round(sum(inv.values()), 2),
               not_="ekran satır tanımını kullanır (kokpit/bütçe ile aynı); fark KDV ve satır dışı kalemlerden")

        # R7 · Tek carinin kitap kırılımı (en büyük cari), rastgele 10 kitap.
        if mk["cariler"]:
            kod = mk["cariler"][0]["kod"]
            s, bk = http("GET", f"/marketplaces/{urllib.parse.quote(kod)}/books?yil={yil}", timeout=1800)
            ref7 = {x["stok"].strip(): (float(x["net_adet"] or 0), float(x["ciro"] or 0)) for x in logo(
                f"SELECT I.CODE AS stok, SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS net_adet, "
                f"SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro "
                f"FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF "
                f"JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF WHERE C.CODE = N'{q(kod)}' AND S.LINETYPE = 0 AND S.CANCELLED = 0 "
                f"AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '{yil}-01-01' "
                f"AND S.DATE_ < '{(son + timedelta(days=1)).isoformat()}' GROUP BY I.CODE")}
            if s != 200:
                record("R7 kitap kırılımı ucu", "DOĞRULANAMADI", durum=s)
            else:
                app7 = {x["stok"]: (x["net"], x["ciro"]) for x in bk["items"]}
                sample = random.sample(sorted(ref7), min(10, len(ref7)))
                bad7 = {k: (app7.get(k), ref7[k]) for k in sample
                        if not app7.get(k) or abs(app7[k][0] - ref7[k][0]) > 1e-6 or abs(app7[k][1] - ref7[k][1]) >= 0.005}
                record("R7 cari kitap kırılımı (10 rastgele)", "OK" if not bad7 and len(app7) == len(ref7) else "FARK", cari=kod,
                       kitap_ekran=len(app7), kitap_referans=len(ref7), farklar=bad7)

    # R4 · Stok: rastgele 20 sitede satıştaki kitap.
    rows = crm(f"SELECT TOP 400 new_ean13 AS ean, new_StokKodu AS stok FROM {p}new_kitapBase WHERE new_tsoftaktif = 1 AND statecode = 0 "
               f"AND new_ean13 IS NOT NULL AND new_StokKodu IS NOT NULL ORDER BY NEWID()")
    checked = bad4 = 0
    bad4_list = []
    for x in rows:
        if checked >= 20:
            break
        ean, code = digits(x["ean"]), str(x["stok"]).strip()
        s, it = http("GET", f"/items/{ean}")
        if s != 200:
            continue
        k = it["kitap"]
        if k.get("stokKodu") != code:
            continue                       # aynı EAN'lı başka kart seçilmiş (çift kayıt) — bu örnek atlanır
        ref4 = logo(f"SELECT SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye "
                    f"FROM dbo.LG_{cur}_01_STLINE L JOIN dbo.LG_{cur}_ITEMS I ON I.LOGICALREF = L.STOCKREF "
                    f"LEFT JOIN dbo.LG_{cur}_01_STFICHE F ON F.LOGICALREF = L.STFICHEREF WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 "
                    f"AND L.IOCODE IN (1,2,3,4) AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1) AND I.CODE = N'{q(code)}'")
        v = float(ref4[0]["bakiye"] or 0) if ref4 else 0.0
        checked += 1
        if k.get("stokLogo") is None or abs(k["stokLogo"] - v) > 1e-6:
            bad4 += 1
            bad4_list.append((code, k.get("stokLogo"), v))
    record("R4 Logo stok (20 rastgele)", "OK" if checked >= 5 and not bad4 else ("DOĞRULANAMADI" if checked < 5 else "FARK"),
           denenen=checked, fark=bad4_list[:10])

    # R5 · Satışta olmaması gereken = Haklar ekranının kuralı (SEO tabloları üzerinde bağımsız sayım).
    with engine.connect() as c:
        ref5 = dict(c.execute(sa.text(
            "SELECT b.status_flag, COUNT(*) FROM semantic_seo_products p JOIN semantic_seo_crm_books b ON b.tenant_id = p.tenant_id "
            "AND b.ean = regexp_replace(coalesce(p.data_json::json->>'Barcode', ''), '[^0-9]', '', 'g') "
            "WHERE p.tenant_id = :t AND p.active AND b.status_flag = ANY(:f) GROUP BY b.status_flag"), {"t": tenant, "f": list(GONE)}).all())
    hak = all_diffs({"tur": "hak", "durum": "acik-hepsi"})
    flagged = [d for d in hak if not str(d.get("crm") or "").startswith("Hak kararı")]
    record("R5 satışta olmaması gereken", "OK" if len(flagged) == sum(ref5.values()) else "FARK", ekran=len(flagged),
           referans=sum(ref5.values()), bayrak=ref5, not_="2026-09-27 ölçümü: bizim değil 247, iptal 55, çekildi 9; aynı barkodlu iki "
           "aktif ürün ekranda tek kitaptır (fark ÖLÇÜM)")

    # R6 · Huni sayaçları: rastgele 10 ürün.
    with engine.connect() as c:
        smp = c.execute(sa.text("SELECT data_json::json->>'Barcode', data_json::json->>'StatViews', data_json::json->>'CountTotalSales' "
                                "FROM semantic_seo_products WHERE tenant_id = :t AND active ORDER BY random() LIMIT 30"), {"t": tenant}).all()
    n6, bad6 = 0, []
    for bc, views, sales in smp:
        if n6 >= 10 or not digits(bc):
            continue
        s, it = http("GET", f"/items/{digits(bc)}")
        if s != 200:
            continue
        k = it["kitap"]
        n6 += 1
        if (k["goruntulenme"], k["siteSatis"]) != (int(float(views or 0)), int(float(sales or 0))):
            bad6.append((digits(bc), k["goruntulenme"], views, k["siteSatis"], sales))
    record("R6 huni sayaçları (10 rastgele)", "OK" if n6 >= 5 and not bad6 else ("DOĞRULANAMADI" if n6 < 5 else "FARK"),
           denenen=n6, fark=bad6[:10], not_="aynı barkodlu iki üründe ekran aktif olanın sayacını gösterir")

    # R8 · Fiyat farklarındaki CRM fiyatı: rastgele 10.
    fiyat = all_diffs({"tur": "fiyat", "durum": "acik-hepsi"})
    n8, bad8 = 0, []
    for d in random.sample(fiyat, min(10, len(fiyat))):
        s, it = http("GET", f"/items/{urllib.parse.quote(d['productKey'])}")
        ref8 = crm(f"SELECT TOP 1 new_kdvdahilfiyat AS f FROM {p}new_kitapBase WHERE new_ean13 = N'{q(d['productKey'])}' "
                   f"ORDER BY CAST(ISNULL(new_tsoftaktif,0) AS int) DESC, statecode ASC, ModifiedOn DESC")
        if s != 200 or not ref8:
            continue
        n8 += 1
        if abs((it["kitap"]["fiyatCrm"] or 0) - float(ref8[0]["f"] or 0)) >= 0.005:
            bad8.append((d["productKey"], it["kitap"]["fiyatCrm"], ref8[0]["f"]))
    record("R8 fiyat farkında CRM fiyatı", "OK" if n8 and not bad8 else ("DOĞRULANAMADI" if not n8 else "FARK"), denenen=n8,
           toplam_fark=len(fiyat), fark=bad8)

    # Ölçülecekler (varsayım → ölçüm): sitedeki fiyat/stok alanlarının doluluğu.
    with engine.connect() as c:
        dol = c.execute(sa.text(
            "SELECT COUNT(*) AS n, "
            "SUM(CASE WHEN coalesce(data_json::json->>'SellingPriceVatIncluded', data_json::json->>'SellingPrice', '') <> '' THEN 1 ELSE 0 END) AS fiyat, "
            "SUM(CASE WHEN coalesce(data_json::json->>'Stock', data_json::json->>'StockCount', '') <> '' THEN 1 ELSE 0 END) AS stok "
            "FROM semantic_seo_products WHERE tenant_id = :t AND active"), {"t": tenant}).mappings().first()
    record("Ö1 sitede fiyat ve stok alanı doluluğu", "ÖLÇÜM", **dict(dol))

    if a.yazma:
        yazma(a)
    return finish(a)


def yazma(a) -> None:
    """İşaret akışı: gerekçesiz bilinçli 422, «sonra» ve geri «açık». Önceki hâl kimlik dosyasında; temizlik.py geri döndürür."""
    open_ = all_diffs({"durum": ""})
    if not open_:
        record("Y işaret akışı", "DOĞRULANAMADI", not_="açık fark yok")
        return
    d = random.choice(open_)
    s, before = http("GET", f"/diffs/{d['id']}")
    Path(a.ids).write_text(json.dumps({"diff": before, "baslangic": time.time()}, ensure_ascii=False, default=str))
    s1, _ = http("POST", f"/diffs/{d['id']}/mark", {"durum": "bilincli"})
    s2, x = http("POST", f"/diffs/{d['id']}/mark", {"durum": "sonra", "note": "kabul testi"})
    s3, y = http("POST", f"/diffs/{d['id']}/mark", {"durum": before["durum"] if before["durum"] in ("acik", "sonra", "bilincli", "duzeltildi") else "acik",
                                                   "note": before.get("not") or ""})
    record("Y işaret akışı", "OK" if (s1, s2, s3) == (422, 200, 200) and x.get("durum") == "sonra" else "FARK",
           durumlar=[s1, s2, s3], fark=d["id"], not_="temizlik.py önceki hâli ve günlüğü geri alır")


def finish(a) -> int:
    Path(a.out).write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str))
    c = {s: sum(1 for r in results if r["durum"] == s) for s in ("OK", "FARK", "DOĞRULANAMADI", "ÖLÇÜM")}
    print(f"== SONUÇ: {c} → {a.out}")
    return 0 if not c["FARK"] and not c["DOĞRULANAMADI"] else 1


if __name__ == "__main__":
    sys.exit(main())
