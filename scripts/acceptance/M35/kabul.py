#!/usr/bin/env python3
"""M35 E-ticaret kampanya yönetimi — test sunucusunda gerçek Logo (.155) + CRM (.28) ile kabul.

Önce gece işi bir kez elle koşturulur ve süresi günlüğe yazılır:

    curl -X POST -H "X-Semantic-Caller: $SEMANTIC_CALLER_TOKEN" http://127.0.0.1:8795/api/v1/kampanya/run-due

Sonra (köprünün sanal ortamında, köprünün env dosyasıyla):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M35/kabul.py --out /tmp/claude-<oturum>/m35-kabul.json
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai)
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M35/kabul.py --api
    # Yazma akışı (KABUL TESTİ taslağı, hesap karşılaştırması, hazırlayan onaylayamaz 409, iptal): kimlikler --ids'e yazılır,
    # temizlik.py siler
    ... kabul.py --api --yazma --ids /tmp/claude-<oturum>/m35-ids.json

Her kontrol: portalın kendi tablolarındaki değer (ekrana giden) ↔ aynı Logo/CRM'de bağımsız SQL (`referans.sql` ile aynı).
Uygulamanın SQL'i yeniden koşturulmaz. Durumlar: OK / FARK / DOĞRULANAMADI / ÖLÇÜM. Yalnız okuma; CRM'e, Logo'ya yazılmaz.
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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import kampanya as K  # noqa: E402
from semantic_bridge import kampanya_sources as src  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
TOL = 0.01  # kuruş / adet


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:600]}")


def close(a, b, tol=TOL) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def q(s: str) -> str:
    return s.replace("'", "''")


def parse_price(v) -> float | None:
    """Bağımsız ayrıştırıcı (referans): «1.250,00» / «45,5» / «45» → sayı."""
    if v is None:
        return None
    t = re.sub(r"[^0-9,.]", "", str(v))
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        x = float(t)
    except ValueError:
        return None
    return x if x > 0 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m35-kabul.json")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--yazma", action="store_true")
    ap.add_argument("--ids", default="m35-ids.json")
    ap.add_argument("--ornek", type=int, default=10, help="kitap başına örnek sayısı (en az 5)")
    args = ap.parse_args()
    n = max(5, args.ornek)

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    K.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    st = K.settings_from(admin_mod.conf)
    logo = src.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = src.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    p = src.prefix(admin_mod.conf("CRM_SCHEMA", "Timas_MSCRM.dbo"))
    firms = src.firms_by_year(logo)
    end = K.data_end(engine)
    refresh = K.meta_get(engine, "refresh")
    record("veri okundu mu", "OK" if end and refresh.get("ok") else "DOĞRULANAMADI", dataEnd=end, son=refresh.get("_at"),
           sure_sn=refresh.get("sn"), uyari=refresh.get("warnings"), fiyatKaydi=K.meta_get(engine, "snapshots"))
    if not end:
        return finish(args)
    year = end.year
    firm = firms.get(year)

    with engine.connect() as c:
        top = c.execute(sa.select(K.BOOKS).where(K.BOOKS.c.ciro_yil.isnot(None)).order_by(K.BOOKS.c.ciro_yil.desc()).limit(n)).all()
        costless = c.execute(sa.select(K.BOOKS).where(K.BOOKS.c.maliyetsiz_satir > 0).order_by(K.BOOKS.c.maliyetsiz_satir.desc()).limit(n)).all()
        velo = c.execute(sa.select(K.BOOKS).where(K.BOOKS.c.adet_son > 0).order_by(K.BOOKS.c.adet_son.desc()).limit(n)).all()
        floors = c.execute(sa.select(K.BOOKS).where(K.BOOKS.c.asgari_fiyat.isnot(None)).limit(n)).all()
        seasoned = c.execute(sa.select(sa.func.count()).select_from(K.BOOKS).where(K.BOOKS.c.sezon_json.isnot(None))).scalar()

    # K1 — kitap marjı (Logo brüt farkı): Σ LINENET − Σ AMOUNT × OUTCOST, satış satırları, güncel yıl kopyası (analiz §14 test 1)
    for b in top:
        ref = logo(f"""SELECT SUM(s.LINENET) - SUM(s.AMOUNT * s.OUTCOST) AS v FROM dbo.LG_{firm}_01_STLINE s
JOIN dbo.LG_{firm}_ITEMS it ON it.LOGICALREF = s.STOCKREF WHERE it.CODE = N'{q(b.stok_kodu)}' AND s.TRCODE IN (7,8,9)
AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND YEAR(s.DATE_) = {year}""")[0]["v"]
        app = (b.ciro_yil or 0) - (b.maliyet_yil or 0)
        record(f"K1 brüt fark {b.stok_kodu}", "OK" if close(app, ref) else "FARK", portal=round(app, 2), referans=ref)

    # K2 — maliyeti girilmemiş satır sayısı (analiz §14 test 2)
    for b in costless[:n]:
        ref = logo(f"""SELECT COUNT(*) AS v FROM dbo.LG_{firm}_01_STLINE s JOIN dbo.LG_{firm}_ITEMS it ON it.LOGICALREF = s.STOCKREF
WHERE it.CODE = N'{q(b.stok_kodu)}' AND s.TRCODE IN (7,8,9) AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0
AND s.OUTCOST = 0 AND YEAR(s.DATE_) = {year}""")[0]["v"]
        record(f"K2 maliyetsiz satır {b.stok_kodu}", "OK" if int(ref or 0) == int(b.maliyetsiz_satir or 0) else "FARK",
               portal=b.maliyetsiz_satir, referans=ref)
    if not costless:
        record("K2 maliyetsiz satır", "ÖLÇÜM", neden="güncel yılda maliyetsiz satış satırı olan kitap yok")

    # K3 — satış hızı: son pencerenin net adedi (Yıl*12+Ay; her yıl kendi firmasından ayrı sorgu)
    win = K.meta_get(engine, "window")
    months = int(win.get("hizAy") or st["hizAy"])
    last = end.year * 12 + end.month - 1
    first = last - months + 1
    for b in velo:
        tot = 0.0
        for y in range(first // 12, last // 12 + 1):
            fy = firms.get(y)
            if not fy:
                continue
            r = logo(f"""SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.AMOUNT ELSE -s.AMOUNT END) AS v FROM dbo.LG_{fy}_01_STLINE s
JOIN dbo.LG_{fy}_ITEMS it ON it.LOGICALREF = s.STOCKREF WHERE it.CODE = N'{q(b.stok_kodu)}' AND s.TRCODE IN (2,3,7,8,9)
AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND YEAR(s.DATE_) = {y}
AND YEAR(s.DATE_) * 12 + MONTH(s.DATE_) - 1 BETWEEN {first} AND {last} AND s.DATE_ <= '{end.isoformat()}'""")
            tot += float(r[0]["v"] or 0)
        record(f"K3 son {months} ay net adet {b.stok_kodu}", "OK" if close(tot, b.adet_son) else "FARK", portal=b.adet_son, referans=tot)

    # K4 — stok bakiyesi (güncel yıl kopyası)
    cur = src.current_firm(firms)
    for b in top[:n]:
        ref = logo(f"""SELECT SUM(CASE WHEN s.IOCODE IN (1,2) THEN s.AMOUNT ELSE -s.AMOUNT END) AS v FROM dbo.LG_{cur}_01_STLINE s
JOIN dbo.LG_{cur}_ITEMS it ON it.LOGICALREF = s.STOCKREF WHERE it.CODE = N'{q(b.stok_kodu)}' AND s.LINETYPE = 0 AND s.CANCELLED = 0
AND s.IOCODE IN (1,2,3,4)""")[0]["v"]
        record(f"K4 stok {b.stok_kodu}", "OK" if close(b.stok, ref or 0) else "FARK", portal=b.stok, referans=ref)

    # K5 — CRM liste fiyatı (KDV dahil) ve sözleşmedeki asgari perakende fiyat (analiz §14 test 7)
    for b in top[:n]:
        ref = crm(f"SELECT TOP 1 new_kdvdahilfiyat AS v FROM {p}new_kitapBase WHERE statecode = 0 AND new_StokKodu = N'{q(b.stok_kodu)}' "
                  "AND new_kdvdahilfiyat IS NOT NULL ORDER BY CASE WHEN new_Tip = 1 THEN 0 ELSE 1 END")
        v = ref[0]["v"] if ref else None
        record(f"K5a CRM liste fiyatı {b.stok_kodu}", "OK" if (v is None and b.liste_crm is None) or close(v, b.liste_crm) else "FARK",
               portal=b.liste_crm, referans=v)
    for b in floors:
        rows = crm(f"""SELECT s.new_MinimumPerakendeSatFiyat AS v FROM {p}new_new_sozlesme_new_kitapBase sk
JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid JOIN {p}new_kitapBase k ON k.new_kitapId = sk.new_kitapid
WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5 AND s.statuscode IN (100000000, 100000006, 100000007) AND k.statecode = 0
AND k.new_StokKodu = N'{q(b.stok_kodu)}'""")
        vals = [x for x in (parse_price(r["v"]) for r in rows) if x]
        ref = max(vals) if vals else None
        record(f"K5b asgari fiyat {b.stok_kodu}", "OK" if close(ref, b.asgari_fiyat) else "FARK", portal=b.asgari_fiyat, referans=ref,
               ham=[r["v"] for r in rows])
    if not floors:
        record("K5b asgari fiyat", "ÖLÇÜM", neden="hiçbir kitapta sözleşme asgari fiyatı okunmadı — alan doluluğu ölçülmeli")
    fill = crm(f"""SELECT COUNT(*) AS toplam, SUM(CASE WHEN s.new_MinimumPerakendeSatFiyat IS NOT NULL AND s.new_MinimumPerakendeSatFiyat <> ''
THEN 1 ELSE 0 END) AS asgari, SUM(CASE WHEN s.new_HesaplamaTipi IS NOT NULL THEN 1 ELSE 0 END) AS hesaplama
FROM {p}new_sozlesmeBase s WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5 AND s.statuscode IN (100000000, 100000006, 100000007)""")[0]
    record("Ö1 sözleşme alanlarının doluluğu", "ÖLÇÜM", **fill)

    # K6 — CRM bayi kampanyaları (analiz §14 test 4) ve kampanya kodlu siparişler (test 5)
    ref_n = crm(f"SELECT COUNT(*) AS v FROM {p}new_kampanyaBase WHERE statecode = 0")[0]["v"]
    ref_rows = crm(f"""SELECT TOP 20 new_kampanyaId AS id, new_name, new_baslangictarihi, new_bitistarihi, new_kampanyamecra, new_netiskonto
FROM {p}new_kampanyaBase WHERE statecode = 0 ORDER BY new_baslangictarihi DESC, new_name""")
    codes = crm(f"""SELECT new_kampanyakodu AS kod, COUNT(*) AS satir, SUM(new_kampanyaindirimtutari) AS indirim FROM {p}new_siparissatiriBase
WHERE new_kampanyakodu IS NOT NULL AND new_kampanyakodu <> '' GROUP BY new_kampanyakodu""")
    record("Ö2 kampanya kodlu sipariş satırı", "ÖLÇÜM", kod=len(codes), satir=sum(int(r["satir"]) for r in codes),
           ornek=sorted(codes, key=lambda r: -int(r["satir"]))[:5])
    by_id = crm(f"""SELECT TOP 20 new_kampanyaid AS id, COUNT(*) AS satir, SUM(new_kampanyaindirimtutari) AS indirim
FROM {p}new_siparissatiriBase WHERE new_kampanyaid IS NOT NULL GROUP BY new_kampanyaid ORDER BY COUNT(*) DESC""")
    record("Ö3 kampanyaya bağlı sipariş satırı (en çok 20)", "ÖLÇÜM", ornek=by_id[:5])

    # K7 — özel gün bağı (analiz §14 test 6): CRM'deki bağ ↔ portalda sezon bağı olan kitap
    link_n = crm(f"SELECT COUNT(*) AS v FROM {p}new_new_kitap_new_ozelgunlerBase")[0]["v"]
    link_books = crm(f"""SELECT COUNT(DISTINCT k.new_StokKodu) AS v FROM {p}new_new_kitap_new_ozelgunlerBase l
JOIN {p}new_kitapBase k ON k.new_kitapId = l.new_kitapid WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL AND k.new_ean13 IS NOT NULL""")[0]["v"]
    record("K7 özel gün bağlı kitap", "OK" if int(seasoned or 0) == int(link_books or 0) else "FARK", portal=seasoned, referans=link_books,
           bag=link_n, not_="fark varsa SEO sezon takviminin okuma kapsamı (barkodlu, T-soft eşleşmesi) incelenir")

    # K8 — site fiyat kaydı: bugünün kaydı ↔ SEO ürün tablosundaki etkin barkodlu ürünler
    snap = K.meta_get(engine, "snapshots")
    record("K8 site fiyat kaydı", "ÖLÇÜM", **{k: snap.get(k) for k in ("urun", "gun", "ilkGun", "sonGun")})

    if args.api:
        api(engine, tenant, args, st, ref_n, ref_rows, top)
    return finish(args)


def api(engine, tenant: str, args, st, ref_n, ref_rows, top) -> None:
    base = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795").rstrip("/")
    cookie = os.environ.get("TIMAS_COOKIE", "")
    if not cookie:
        record("API", "DOĞRULANAMADI", neden="TIMAS_COOKIE yok")
        return

    def call(method: str, path: str, body=None):
        req = urllib.request.Request(base + path, method=method, headers={"cookie": cookie, "Content-Type": "application/json"},
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    code, ov = call("GET", "/api/v1/kampanya/overview")
    record("A1 genel görünüm", "OK" if code == 200 else "FARK", durum=code, takvim=len((ov or {}).get("takvim", {}).get("items", [])) if code == 200 else None)
    code, crm_page = call("GET", "/api/v1/kampanya/crm-campaigns?page=0&etkin=true")
    if code == 200:
        same = [r["id"].lower() for r in ref_rows] == [x["id"] for x in crm_page["items"][:20]]
        record("A2 CRM bayi kampanyaları (sayı + ilk 20)", "OK" if crm_page["total"] == int(ref_n) and same else "FARK",
               api=crm_page["total"], referans=ref_n, ilk20_ayni=same)
    else:
        record("A2 CRM bayi kampanyaları", "FARK", durum=code, cevap=crm_page)
    code, cand = call("GET", "/api/v1/kampanya/candidates?kurallar=stok,dusus,hak")
    record("A3 aday listesi (tavansız toplam)", "OK" if code == 200 else "FARK", durum=code, toplam=(cand or {}).get("total") if code == 200 else None)
    if not args.yazma:
        return

    ids = {"campaigns": [], "calendar": []}
    books = [b.stok_kodu for b in top if (b.liste_crm or b.liste_logo)][:3]
    code, c = call("POST", "/api/v1/kampanya/campaigns", {"ad": "KABUL TESTİ kampanya", "kanal": "site",
                                                            "baslangic": (date.today() + timedelta(days=30)).isoformat(),
                                                            "bitis": (date.today() + timedelta(days=37)).isoformat(), "varsayilanIndirim": 20})
    if code != 201:
        record("Y1 taslak açma", "FARK", durum=code, cevap=c)
        Path(args.ids).write_text(json.dumps(ids))
        return
    ids["campaigns"].append(c["id"])
    Path(args.ids).write_text(json.dumps(ids))
    code, c = call("POST", f"/api/v1/kampanya/campaigns/{c['id']}/items", {"kitaplar": [{"stok": s} for s in books]})
    record("Y2 kitap ekleme", "OK" if code == 200 and len(c.get("kitaplar", [])) == len(books) else "FARK", durum=code)
    # Y3 — hesap: ekrandaki kampanya fiyatı ve marj ↔ kitap tablosundan elle hesap (liste × 0,8; net − maliyet − telif)
    with engine.connect() as cn:
        rows = {b.stok_kodu: b for b in cn.execute(sa.select(K.BOOKS).where(K.BOOKS.c.stok_kodu.in_(books))).all()}
    for it in (c.get("kitaplar") or []):
        b = rows[it["stok"]]
        liste = b.liste_crm if st["listPriceSource"] == "crm" and b.liste_crm else (b.liste_logo or b.liste_crm)
        exp_kf = round(liste * 0.8, 2)
        ok = close(it["kampanyaFiyati"], exp_kf)
        if it["birimMaliyet"] is not None and it["telifSonra"] is not None:
            exp_m = exp_kf / (1 + (b.kdv or 0) / 100) - it["birimMaliyet"] - it["telifSonra"]
            ok = ok and close(it["marjSonra"], exp_m, 0.02)
        record(f"Y3 hesap {it['stok']}", "OK" if ok else "FARK", kampanyaFiyati=it["kampanyaFiyati"], beklenen=exp_kf,
               marj=it["marjSonra"], maliyetKaynak=it["maliyetKaynak"], kontroller=[k["mesaj"] for k in it["kontroller"]][:4])
    code, s = call("POST", f"/api/v1/kampanya/campaigns/{c['id']}/submit", {})
    record("Y4 onaya gönder", "OK" if code == 200 and s.get("durum") == "onay_bekliyor" else "FARK", durum=code, bildirim=(s or {}).get("bildirim"))
    code, d = call("POST", f"/api/v1/kampanya/campaigns/{c['id']}/decision", {"karar": "onay"})
    record("Y5 gönderen onaylayamaz", "OK" if code in (409, 403) else "FARK", durum=code, cevap=d)
    code, x = call("POST", f"/api/v1/kampanya/campaigns/{c['id']}/cancel", {"not": "Kabul testi"})
    record("Y6 iptal", "OK" if code == 200 and x.get("durum") == "iptal" else "FARK", durum=code)
    code, x = call("POST", "/api/v1/kampanya/campaigns", {})
    record("Y7 boş gövde 400", "OK" if code in (400, 422) else "FARK", durum=code)
    Path(args.ids).write_text(json.dumps(ids))
    print(f"Kimlikler {args.ids} dosyasında; temizlik: python3 ../scripts/acceptance/M35/temizlik.py --ids {args.ids}")


def finish(args) -> int:
    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
    bad = [r for r in RESULTS if r["durum"] == "FARK"]
    unv = [r for r in RESULTS if r["durum"] == "DOĞRULANAMADI"]
    print(f"\nToplam {len(RESULTS)} · FARK {len(bad)} · DOĞRULANAMADI {len(unv)} · sonuç {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
