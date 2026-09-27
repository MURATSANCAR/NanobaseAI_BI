#!/usr/bin/env python3
"""M32 Kurumsal satış ve B2B — test sunucusunda gerçek Logo/CRM ile kabul.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla; önce bir kez `run-due` elle koşturulmuş olmalı):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M32/kabul.py --out /tmp/claude-<oturum>/m32-kabul.json
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai)
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M32/kabul.py --api
    # Yazma akışı (fırsat + teklif, gönderen onaylayamaz 409): kimlikler --ids dosyasına yazılır, temizlik.py siler
    ... kabul.py --api --yazma --ids /tmp/claude-<oturum>/m32-ids.json

Her kontrol: OK / FARK / DOĞRULANAMADI. Portal tarafı köprünün kendi tablolarından (uygulamanın ekrana verdiği değer) ya da
API'den okunur; referans aynı Logo/CRM'de bağımsız SQL'dir (referans.sql). Uygulamanın SQL'i yeniden koşturulmaz.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import corporate_sales as C  # noqa: E402
from semantic_bridge import corporate_sales_sources as S  # noqa: E402
from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
TOL = 0.01  # kuruş


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:400]}")


def close(a, b, tol=TOL) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def q(s: str) -> str:
    return s.replace("'", "''")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m32-kabul.json")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--yazma", action="store_true")
    ap.add_argument("--ids", default="m32-ids.json")
    ap.add_argument("--ornek", type=int, default=5, help="kitap/kurum/bayi başına örnek sayısı (en az 5)")
    args = ap.parse_args()
    n = max(5, args.ornek)

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    C.ensure(engine)
    admin_mod.ensure(engine)  # ayarlar ekrandaki değerleriyle okunsun
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    st = C.settings_from(admin_mod.conf)
    channel = S.channel_list(st["channel"])[0]
    dealers = S.channel_list(",".join(st["dealerChannels"]))
    logo = S.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    schema = admin_mod.conf("CRM_SCHEMA", "Timas_MSCRM.dbo")
    firms = S.firms_by_year(logo)
    cur = S.current_firm(firms)
    end = C.data_end(engine)
    refresh = C.meta_get(engine, "refresh")
    record("veri okundu mu", "OK" if end and refresh.get("ok") else "DOĞRULANAMADI", dataEnd=end, son=refresh.get("_at"),
           uyari=refresh.get("warnings"))
    if not end:
        return finish(args)
    year = end.year

    # K1 — KURUM net ciro (yıl)
    ref = logo(f"""SELECT SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) AS v
FROM dbo.LG_{cur}_01_STLINE L JOIN dbo.LG_{cur}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
WHERE C.SPECODE2 = N'{q(channel)}' AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)
  AND L.DATE_ >= '{year}-01-01' AND L.DATE_ < '{year + 1}-01-01'""")[0]["v"]
    with engine.connect() as c:
        app = c.execute(sa.select(sa.func.sum(C.SALES.c.ciro)).where(C.SALES.c.year == year)).scalar()
    record(f"K1 KURUM net ciro {year}", "OK" if close(app, ref, 1.0) else "FARK", portal=app, referans=ref)

    # K2 — kurum başına satış faturası sayısı (en çok alan n kurum)
    with engine.connect() as c:
        top = c.execute(sa.select(C.SALES.c.logo_code, sa.func.sum(C.SALES.c.fatura).label("f"), sa.func.sum(C.SALES.c.ciro).label("z"))
                        .where(C.SALES.c.year == year).group_by(C.SALES.c.logo_code).order_by(sa.desc("z")).limit(n)).all()
    for r in top:
        ref = logo(f"""SELECT COUNT(DISTINCT I.LOGICALREF) AS v FROM dbo.LG_{cur}_01_INVOICE I
JOIN dbo.LG_{cur}_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE C.CODE = N'{q(r.logo_code)}' AND I.CANCELLED = 0 AND I.TRCODE IN (7,8,9)
  AND I.DATE_ >= '{year}-01-01' AND I.DATE_ < '{year + 1}-01-01'""")[0]["v"]
        record(f"K2 fatura sayısı {r.logo_code}", "OK" if int(ref or 0) == int(r.f or 0) else "FARK", portal=r.f, referans=ref)

    # K3 — B2B portal siparişi, son N gün (CRM)
    try:
        crm = S.runner(crm_file)
        p = S.prefix(schema)
        ref_all = crm(f"SELECT COUNT(*) AS v FROM {p}new_siparisBase s WHERE s.statecode = 0 AND s.new_yenib2b = 1 "
                      f"AND s.CreatedOn >= DATEADD(day, -{st['b2bDays']}, GETDATE())")[0]["v"]
        ref_type = crm(f"SELECT COUNT(*) AS v FROM {p}new_siparisBase s WHERE s.statecode = 0 AND s.new_yenib2b = 1 "
                       f"AND s.new_siparistipi = 1 AND s.CreatedOn >= DATEADD(day, -{st['b2bDays']}, GETDATE())")[0]["v"]
        with engine.connect() as c:
            app = c.execute(sa.select(sa.func.sum(C.DEALERS.c.b2b_siparis))).scalar() or 0
            codes = [r[0] for r in c.execute(sa.select(C.DEALERS.c.logo_code).where(C.DEALERS.c.b2b_siparis > 0)
                                             .order_by(C.DEALERS.c.b2b_siparis.desc()).limit(n)).all()]
        record("K3 B2B sipariş toplamı (bayi listesindekiler ≤ CRM toplamı)", "OK" if app <= ref_all else "FARK",
               portal_bayi_listesi=app, crm_toplam=ref_all, crm_tip1=ref_type, olcum_2026_09_27=4026,
               not_="bayi listesi yalnız son 12 ayda Logo faturası olan bayi/kitapçı carilerini kapsar")
        for code in codes:
            ref = crm(f"SELECT COUNT(*) AS v FROM {p}new_siparisBase s JOIN {p}AccountBase a ON a.AccountId = s.new_firmaid "
                      f"WHERE s.statecode = 0 AND s.new_yenib2b = 1 AND s.CreatedOn >= DATEADD(day, -{st['b2bDays']}, GETDATE()) "
                      f"AND a.new_CariKodu = N'{q(code)}'")[0]["v"]
            with engine.connect() as c:
                app1 = c.execute(sa.select(C.DEALERS.c.b2b_siparis).where(C.DEALERS.c.logo_code == code)).scalar()
            record(f"K3 B2B sipariş {code}", "OK" if int(ref or 0) == int(app1 or 0) else "FARK", portal=app1, referans=ref,
                   not_="gece okumasından bu yana yeni sipariş gelmişse küçük fark beklenir")
    except S.SourceError as e:
        record("K3 B2B sipariş", "DOĞRULANAMADI", hata=str(e))

    # K4 — paket fiyatı ve stok (fiyatlı, stoklu n kitap)
    with engine.connect() as c:
        books = c.execute(sa.select(C.BOOKS).where(C.BOOKS.c.fiyat.isnot(None), C.BOOKS.c.stok > 0)
                          .order_by(C.BOOKS.c.yil_adet.desc()).limit(n)).all()
    today = C.today().isoformat()
    for b in books:
        rows = logo(f"""SELECT P.CODE AS liste, P.PRICE AS fiyat, P.PRIORITY AS oncelik, P.INCVAT AS kdv_dahil, P.CLSPECODE AS cari_ozel,
  P.CLIENTCODE AS cari, P.BEGDATE AS bas
FROM dbo.LG_{cur}_PRCLIST P JOIN dbo.LG_{cur}_ITEMS I ON I.LOGICALREF = P.CARDREF
WHERE I.CODE = N'{q(b.stok_kodu)}' AND P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY = 160 AND P.BEGDATE <= '{today}'
  AND (P.ENDDATE >= '{today}' OR P.ENDDATE IS NULL)""")
        pick = S.pick_price(rows)
        ok = pick and close(pick["fiyat"], b.fiyat) and pick["liste"] == b.fiyat_liste and pick["listeSayisi"] == b.fiyat_liste_sayisi
        record(f"K4 liste fiyatı {b.stok_kodu}", "OK" if ok else "FARK", portal=[b.fiyat, b.fiyat_liste, b.fiyat_liste_sayisi],
               referans=[pick and pick["fiyat"], pick and pick["liste"], len(rows)], gecerli_listeler=len(rows))
        bal = logo(f"""SELECT SUM(CASE WHEN S.IOCODE IN (1,2) THEN S.AMOUNT ELSE -S.AMOUNT END) AS v
FROM dbo.LG_{cur}_01_STLINE S JOIN dbo.LG_{cur}_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE I.CODE = N'{q(b.stok_kodu)}' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.IOCODE IN (1,2,3,4)""")[0]["v"]
        record(f"K4 stok {b.stok_kodu}", "OK" if close(bal, b.stok, 0.001) else "FARK", portal=b.stok, referans=bal)

    # K5 — birim maliyet: M9 bağlı değilse «bilinmiyor»; logo kaynağında son maliyetli satır
    costs = C.costs_for(engine, st, [b.stok_kodu for b in books])
    if st["costSource"] == "logo":
        for b in books:
            r = logo(f"""SELECT TOP 1 S.OUTCOST AS v FROM dbo.LG_{cur}_01_STLINE S JOIN dbo.LG_{cur}_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE I.CODE = N'{q(b.stok_kodu)}' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9) AND S.OUTCOST <> 0
ORDER BY S.DATE_ DESC, S.LOGICALREF DESC""")
            ref = r[0]["v"] if r else None
            record(f"K5 tahmini maliyet {b.stok_kodu}", "OK" if (ref is None and costs[b.stok_kodu]["birim"] is None)
                   or close(ref, costs[b.stok_kodu]["birim"], 0.0001) else "FARK", portal=costs[b.stok_kodu], referans=ref)
    else:
        unknown = all(v["birim"] is None for v in costs.values()) if st["costSource"] == "m9" and S._COST_PROVIDER is None else None
        record("K5 maliyet kaynağı", "OK" if unknown in (True, None) else "FARK", kaynak=st["costSource"],
               m9_bagli=S._COST_PROVIDER is not None, ornek=list(costs.values())[:2])

    # K6 — sessiz bayi listesi
    R = end
    ref_codes: dict[str, date] = {}
    counts: dict[str, int] = {}
    for firm, a, b_ in S.firm_ranges(firms, R - timedelta(days=365), R + timedelta(days=1)):
        for r in logo(f"""SELECT C.CODE AS kod, MAX(I.DATE_) AS son, COUNT(*) AS f
FROM dbo.LG_{firm}_01_INVOICE I JOIN dbo.LG_{firm}_CLCARD C ON C.LOGICALREF = I.CLIENTREF
WHERE C.SPECODE2 IN ({', '.join("N'" + q(x) + "'" for x in dealers)}) AND I.CANCELLED = 0 AND I.TRCODE IN (7,8,9)
  AND I.DATE_ >= '{a.isoformat()}' AND I.DATE_ < '{b_.isoformat()}' GROUP BY C.CODE"""):
            d = S.day(r["son"])
            k = str(r["kod"]).strip()
            if d and (k not in ref_codes or d > ref_codes[k]):
                ref_codes[k] = d
            counts[k] = counts.get(k, 0) + int(r["f"] or 0)
    silent_ref = {k for k, d in ref_codes.items() if (R - d).days >= st["silentDays"] and counts.get(k, 0) >= 1}
    silent_app = {i["logoKod"] for i in C.dealer_rows(engine, gun=st["silentDays"], durum="sessiz")["items"]}
    record(f"K6 sessiz bayi ({st['silentDays']} gün)", "OK" if silent_ref == silent_app else "FARK",
           portal=len(silent_app), referans=len(silent_ref), yalniz_portal=sorted(silent_app - silent_ref)[:20],
           yalniz_referans=sorted(silent_ref - silent_app)[:20])

    # K7 — hacim indirimi medyanı (100–299 adet)
    vol = C.meta_get(engine, "volume").get("buckets") or []
    b100 = next((x for x in vol if x["min"] == 100), None)
    if b100:
        w0, w1 = (R - timedelta(days=365)).isoformat(), (R + timedelta(days=1)).isoformat()
        rows = []
        for firm, a, b_ in S.firm_ranges(firms, R - timedelta(days=365), R + timedelta(days=1)):
            rows += logo(f"""SELECT SUM(S.AMOUNT) AS adet, SUM(S.TOTAL) AS brut, SUM(S.LINENET) AS net
FROM dbo.LG_{firm}_01_STLINE S JOIN dbo.LG_{firm}_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE C.SPECODE2 = N'{q(channel)}' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9)
  AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b_.isoformat()}' GROUP BY S.INVOICEREF""")
        hi = next((x["min"] for x in vol if x["min"] > 100), None)
        rates = sorted(1 - float(r["net"]) / float(r["brut"]) for r in rows
                       if float(r["brut"] or 0) > 0 and float(r["adet"] or 0) >= 100 and (hi is None or float(r["adet"]) < hi))
        med = (rates[len(rates) // 2] if len(rates) % 2 else (rates[len(rates) // 2 - 1] + rates[len(rates) // 2]) / 2) if rates else None
        med = max(0.0, min(1.0, med)) if med is not None else None
        ok = (b100["indirim"] is None and len(rates) < st["volumeMinN"]) or close(b100["indirim"], med, 0.0001)
        record("K7 hacim indirimi medyanı 100 adet aralığı", "OK" if ok else "FARK", portal=b100, referans={"medyan": med, "n": len(rates)},
               pencere=[w0, w1])
    else:
        record("K7 hacim indirimi medyanı", "DOĞRULANAMADI", neden="hacim geçmişi okunmamış")

    # K8 — kurum sayısı
    ref = logo(f"SELECT COUNT(*) AS v FROM dbo.LG_{cur}_CLCARD WHERE SPECODE2 = N'{q(channel)}'")[0]["v"]
    with engine.connect() as c:
        app = c.execute(sa.select(sa.func.count()).select_from(C.ACCOUNTS).where(
            C.ACCOUNTS.c.tenant_id == tenant, C.ACCOUNTS.c.kanal == channel)).scalar()
    record("K8 Logo kurum carisi sayısı", "OK" if int(ref) == int(app) else "FARK", portal=app, referans=ref)

    if args.api:
        api_checks(args, st, end)
    return finish(args)


def http(method: str, path: str, body=None):
    url = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795") + path
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Cookie": os.environ.get("TIMAS_COOKIE", ""), "Content-Type": "application/json",
                                          "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


def api_checks(args, st: dict, end: date) -> None:
    P = "/api/v1/corporate"
    code, s = http("GET", f"{P}/summary")
    record("API özet", "OK" if code == 200 else "FARK", durum=code)
    if code == 200:
        record("API özet veri sonu = köprü tablosu", "OK" if s.get("dataEnd") == end.isoformat() else "FARK", api=s.get("dataEnd"), tablo=end)
    for path in ("/accounts", "/opportunities", "/reminders", "/b2b/dealers?durum=sessiz", "/b2b/highlights", "/themes"):
        code, _ = http("GET", P + path)
        record(f"API GET {path}", "OK" if code in (200, 403) else "FARK", durum=code)
    # Geçersiz gövdeler: yazma uçları önce boş gövdeyle (400/422) denenir.
    for path in ("/opportunities", "/packages/suggest"):
        code, body = http("POST", P + path, {})
        record(f"API POST {path} boş gövde", "OK" if code in (400, 403, 422) else "FARK", durum=code, mesaj=str(body)[:160])
    code, _ = http("GET", f"{P}/quotes/yok")
    record("API olmayan teklif 404", "OK" if code in (404, 403) else "FARK", durum=code)
    if not args.yazma:
        return
    ids = {"opportunities": [], "quotes": []}
    try:
        code, o = http("POST", f"{P}/opportunities", {"kurum": "KABUL TESTİ (silinecek)", "ad": "M32 kabul"})
        record("API fırsat aç", "OK" if code == 201 else "FARK", durum=code)
        if code != 201:
            return
        ids["opportunities"].append(o["id"])
        code, b = http("GET", f"{P}/books?q=a")
        stok = (b.get("items") or [{}])[0].get("stokKodu") if code == 200 else None
        if not stok:
            record("API teklif için kitap", "DOĞRULANAMADI")
            return
        code, qt = http("POST", f"{P}/opportunities/{o['id']}/quotes", {"kalemler": [{"stok": stok, "adet": 1, "indirim": 99}]})
        record("API teklif aç (%99 indirim)", "OK" if code == 201 else "FARK", durum=code)
        if code != 201:
            return
        ids["quotes"].append(qt["id"])
        code, qt = http("POST", f"{P}/quotes/{qt['id']}/submit")
        record("API eşik üstü teklif onaya düşer", "OK" if code == 200 and qt.get("durum") == "onayda" else "FARK", durum=code)
        code, r = http("POST", f"{P}/quotes/{qt['id']}/approve", {})
        record("API gönderen onaylayamaz (409) ya da yetkisi yok (403)", "OK" if code in (403, 409) else "FARK", durum=code,
               mesaj=str(r)[:160])
        code, _ = http("POST", f"{P}/quotes/{qt['id']}/withdraw")
        record("API taslağa geri al", "OK" if code == 200 else "FARK", durum=code)
        for ext in ("pdf", "xlsx"):
            code, data = http("GET", f"{P}/quotes/{qt['id']}/document.{ext}")
            record(f"API teklif belgesi {ext}", "OK" if code == 200 and isinstance(data, bytes) and len(data) > 500 else "FARK",
                   durum=code, boyut=len(data) if isinstance(data, bytes) else None)
    finally:
        Path(args.ids).write_text(json.dumps(ids, ensure_ascii=False))
        print(f"Silinecek kimlikler: {args.ids} → temizlik.py")


def finish(args) -> int:
    Path(args.out).write_text(json.dumps({"zaman": datetime.now().isoformat(), "sonuc": RESULTS}, ensure_ascii=False, indent=1, default=str))
    bad = [r for r in RESULTS if r["durum"] != "OK"]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} OK · FARK {sum(r['durum'] == 'FARK' for r in RESULTS)} · "
          f"DOĞRULANAMADI {sum(r['durum'] == 'DOĞRULANAMADI' for r in RESULTS)} → {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
