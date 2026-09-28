#!/usr/bin/env python3
"""M53 Set, hediye ve promosyon — test sunucusunda gerçek Logo (.155) + CRM (.28) ile ölçüm ve kabul.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla; önce bir kez `run-due` elle koşturulmuş olmalı —
`curl -X POST -H "X-Semantic-Caller: $SEMANTIC_CALLER_TOKEN" 'http://127.0.0.1:8795/api/v1/marketing/sets/run-due?basket=1&history=1'`
ve süresi günlüğe yazılır):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M53/kabul.py --olcum --out /tmp/claude-<oturum>/m53-kabul.json
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai)
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M53/kabul.py --api
    # Yazma akışı (taslak set, gönderen onaylayamaz 409, sil): kimlikler --ids dosyasına yazılır, temizlik.py siler
    ... kabul.py --api --yazma --ids /tmp/claude-<oturum>/m53-ids.json

Bölümler:
- **Ö (ölçüm, --olcum):** kodlamadan önce ölçülmesi gerekenler — setin Logo'daki temsili (kart türü, reçete, CRM set
  işlemi), aynı faturada set + bileşen satırı (çift sayım riski), set faturalarının satır türleri (karma koli 6/7 var mı),
  B2C siparişlerinin CRM'deki kapsamı, 157 kodları, hediye/promosyon bayraklarının doluluğu, sepet sorgusunun süresi.
  Sonuç analiz belgesine (M53 §6, §14) ve günlüğe yazılır; varsayılan ayar ölçüme göre değişebilir.
- **K (kabul):** portalın kendi tablolarındaki değer (ekrana giden) ↔ aynı Logo/CRM'de bağımsız SQL (referans.sql).
  Uygulamanın SQL'i yeniden koşturulmaz. Her kontrol: OK / FARK / DOĞRULANAMADI / ÖLÇÜM.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import sets as S  # noqa: E402
from semantic_bridge import sets_sources as src  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
TOL = 0.01  # kuruş


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:500]}")


def close(a, b, tol=TOL) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def q(s: str) -> str:
    return s.replace("'", "''")


def inlist(codes) -> str:
    return ", ".join("N'" + q(c) + "'" for c in codes) or "N'-'"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m53-kabul.json")
    ap.add_argument("--olcum", action="store_true")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--yazma", action="store_true")
    ap.add_argument("--ids", default="m53-ids.json")
    ap.add_argument("--ornek", type=int, default=5, help="set/çift başına örnek sayısı (en az 5)")
    args = ap.parse_args()
    n = max(5, args.ornek)

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    S.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    st = S.settings_from(admin_mod.conf)
    logo = src.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    crm = src.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    p = src.prefix(admin_mod.conf("CRM_SCHEMA", "Timas_MSCRM.dbo"))
    firms = src.firms_by_year(logo)
    cur = src.current_firm(firms)
    end = S.data_end(engine)
    refresh = S.meta_get(engine, "refresh")
    record("veri okundu mu", "OK" if end and refresh.get("ok") else "DOĞRULANAMADI", dataEnd=end, son=refresh.get("_at"),
           sure_sn=refresh.get("sn"), uyari=refresh.get("warnings"), sepet=S.meta_get(engine, "basket"))
    crm_set_codes = [r["stok"] for r in crm(f"SELECT new_StokKodu AS stok FROM {p}new_kitapBase WHERE statecode = 0 AND new_Tip = 4 "
                                              f"AND new_StokKodu IS NOT NULL") if r.get("stok")]

    if args.olcum:
        olcum(logo, crm, p, cur, end, st, crm_set_codes, n)
    if not end:
        return finish(args)

    # K1 — set envanteri: CRM set kartı sayısı = portalda CRM kartına bağlı (kapanmamış) set sayısı
    ref_all = crm(f"SELECT COUNT(*) AS v FROM {p}new_kitapBase WHERE statecode = 0 AND new_Tip = 4")[0]["v"]
    with engine.connect() as c:
        app = c.execute(sa.select(sa.func.count()).select_from(S.SETS).where(S.SETS.c.tenant_id == tenant, S.SETS.c.crm_kitap_id.isnot(None),
                                                                           S.SETS.c.durum != "kapandi")).scalar()
    record("K1 CRM set kartı sayısı", "OK" if int(app or 0) == len(set(crm_set_codes)) else "FARK", portal=app,
           referans_stok_kodlu=len(set(crm_set_codes)), referans_tumu=ref_all,
           not_="stok kodu boş set kartı portala giremez; fark varsa ekranda «stok kodu yok» olarak raporlanır")

    # K2 — bileşenler: en son etkin Set Yapma işleminin alt mamul satırları = semantic_mkt_set_items
    with engine.connect() as c:
        sample = c.execute(sa.select(S.SETS.c.id, S.SETS.c.stok_kodu).where(S.SETS.c.bilesen_kaynak == "crm-set-islemi")
                           .order_by(S.SETS.c.id).limit(n)).all()
        items = S._items_of(c, [r.id for r in sample])
    if not sample:
        record("K2 bileşenler (CRM set işlemi)", "DOĞRULANAMADI", neden="CRM set işlemi olan set yok")
    for r in sample:
        ref = crm(f"""WITH son AS (SELECT TOP 1 si.new_setislemiId AS islem FROM {p}new_setislemiBase si
JOIN {p}ProductBase ps ON ps.ProductId = si.new_urunid
WHERE ps.ProductNumber = N'{q(r.stok_kodu)}' AND si.statecode = 0 AND si.new_islemtipi = 1 ORDER BY si.CreatedOn DESC)
SELECT p.ProductNumber AS stok, SUM(sl.new_adet) AS adet FROM son
JOIN {p}new_setislemisatiriBase sl ON sl.new_setislemiid = son.islem JOIN {p}ProductBase p ON p.ProductId = sl.new_urunid
WHERE sl.new_tip = 2 AND sl.statecode = 0 GROUP BY p.ProductNumber""")
        want = {x["stok"]: round(float(x["adet"] or 0), 4) for x in ref}
        got = {i.stok_kodu: round(i.adet, 4) for i in items.get(r.id, [])}
        record(f"K2 bileşenler {r.stok_kodu}", "OK" if want == got else "FARK", portal=got, referans=want)

    # K3 — set satışı: set kodu × yıl net adet / net ciro (faturalı satır, iade eksi), kuruşu kuruşuna
    lt = ", ".join(str(x) for x in st["salesLinetypes"])
    with engine.connect() as c:
        top = c.execute(sa.select(S.SALES.c.stok_kodu, sa.func.sum(S.SALES.c.net_ciro).label("z")).where(S.SALES.c.tur == "set")
                        .group_by(S.SALES.c.stok_kodu).order_by(sa.desc("z")).limit(n)).all()
    for y in sorted({end.year, end.year - 1}):
        firm = firms.get(y)
        if not firm:
            continue
        for r in top:
            ref = logo(f"""SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro
FROM dbo.LG_{firm}_01_STLINE S JOIN dbo.LG_{firm}_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE I.CODE = N'{q(r.stok_kodu)}' AND S.CANCELLED = 0 AND S.LINETYPE IN ({lt}) AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{y}-01-01' AND S.DATE_ < '{y + 1}-01-01'""")[0]
            with engine.connect() as c:
                app = c.execute(sa.select(sa.func.sum(S.SALES.c.net_adet), sa.func.sum(S.SALES.c.net_ciro)).where(
                    S.SALES.c.stok_kodu == r.stok_kodu, S.SALES.c.yil_ay.like(f"{y}-%"))).first()
            ok = close(app[1] or 0, ref["ciro"] or 0) and close(app[0] or 0, ref["adet"] or 0, 0.0001)
            record(f"K3 set satışı {r.stok_kodu} {y}", "OK" if ok else "FARK", portal={"adet": app[0], "ciro": app[1]}, referans=ref)

    # K4 — liste toplamı: Σ CRM KDV dahil fiyat × adet = liste_toplami (kaynak crm iken); Logo listesiyle fark ayrıca
    with engine.connect() as c:
        sample = c.execute(sa.select(S.SETS).where(S.SETS.c.liste_toplami.isnot(None)).order_by(S.SETS.c.id).limit(n)).all()
        items = S._items_of(c, [r.id for r in sample])
    for r in sample:
        its = items.get(r.id, [])
        ref = crm(f"SELECT new_StokKodu AS stok, new_kdvdahilfiyat AS f FROM {p}new_kitapBase WHERE statecode = 0 "
                  f"AND new_StokKodu IN ({inlist([i.stok_kodu for i in its])})")
        price = {x["stok"]: float(x["f"]) for x in ref if x.get("f")}
        want = sum(price.get(i.stok_kodu, 0) * i.adet for i in its) if all(i.stok_kodu in price for i in its) else None
        status = "OK" if (st["listPriceSource"] == "crm" and close(r.liste_toplami, want)) else (
            "ÖLÇÜM" if st["listPriceSource"] == "logo" else "FARK")
        record(f"K4 liste toplamı {r.id}", status, portal=r.liste_toplami, referans_crm=want, logo=r.liste_toplami_logo)

    # K5 — birlikte alım çifti: seçilen çiftin B2C sipariş sayısı (aynı süzgeç, referans.sql R5)
    basket = S.meta_get(engine, "basket")
    with engine.connect() as c:
        pairs = c.execute(sa.select(S.PAIRS).order_by(S.PAIRS.c.siparis_sayisi.desc()).limit(n)).all()
    if not pairs:
        record("K5 birlikte alım", "DOĞRULANAMADI", neden="çift yok", sepet=basket)
    types = ", ".join(str(t) for t in st["b2cTypes"]) or "-1"
    pre = st["b2cPrefix"]
    since = (basket.get("donem") or [None])[0]
    for r in pairs:
        ref = crm(f"""SELECT COUNT(DISTINCT s.new_siparisId) AS v FROM {p}new_siparisBase s
JOIN {p}new_siparissatiriBase a ON a.new_siparisid = s.new_siparisId JOIN {p}ProductBase pa ON pa.ProductId = a.new_urunid
JOIN {p}new_siparissatiriBase b ON b.new_siparisid = s.new_siparisId JOIN {p}ProductBase pb ON pb.ProductId = b.new_urunid
WHERE (s.new_siparistipi IN ({types}) OR LEFT(s.new_name, {len(pre)}) = N'{q(pre)}') AND s.statuscode NOT IN (1, 100000001)
  AND pa.ProductNumber = N'{q(r.kod_a)}' AND pb.ProductNumber = N'{q(r.kod_b)}' AND s.new_siparistarihi >= '{since}'
  AND a.statuscode <> 100000001 AND b.statuscode <> 100000001
  AND ISNULL(a.new_promosyon, 0) = 0 AND ISNULL(a.new_kesinhediye, 0) = 0 AND ISNULL(a.new_bedelsiz, 0) = 0
  AND ISNULL(b.new_promosyon, 0) = 0 AND ISNULL(b.new_kesinhediye, 0) = 0 AND ISNULL(b.new_bedelsiz, 0) = 0""")[0]["v"]
        record(f"K5 çift {r.kod_a}+{r.kod_b}", "OK" if int(ref or 0) == r.siparis_sayisi else "FARK", portal=r.siparis_sayisi, referans=ref)

    # K6 — promosyon ürünleri: 157 kart sayısı ve bu yılın faturalı satışı
    pre157 = st["promoPrefix"]
    ref_n = logo(f"SELECT COUNT(*) AS v FROM dbo.LG_{cur}_ITEMS WHERE CODE LIKE '{q(pre157)}%'")[0]["v"]
    with engine.connect() as c:
        app_n = c.execute(sa.select(sa.func.count()).select_from(S.PROMO).where(S.PROMO.c.tur == "157")).scalar()
        app_z = c.execute(sa.select(sa.func.sum(S.SALES.c.net_ciro)).where(S.SALES.c.stok_kodu.like(f"{pre157}%"),
                                                                           S.SALES.c.yil_ay.like(f"{end.year}-%"))).scalar()
    record("K6a 157 kart sayısı", "OK" if int(ref_n or 0) == int(app_n or 0) else "FARK", portal=app_n, referans=ref_n)
    ref_z = logo(f"""SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS v
FROM dbo.LG_{firms[end.year]}_01_STLINE S JOIN dbo.LG_{firms[end.year]}_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE I.CODE LIKE '{q(pre157)}%' AND S.CANCELLED = 0 AND S.LINETYPE IN ({lt}) AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{end.year}-01-01' AND S.DATE_ < '{end.year + 1}-01-01'""")[0]["v"]
    record(f"K6b 157 net ciro {end.year}", "OK" if close(app_z or 0, ref_z or 0, 1.0) else "FARK", portal=app_z, referans=ref_z)

    # K7 — marj hesabı: KDV hariç gelir bağımsız hesap (Logo SELLVAT + liste payı); maliyet yoksa marj yok ve mesaj
    with engine.connect() as c:
        sample = c.execute(sa.select(S.SETS).where(S.SETS.c.set_fiyati > 0, S.SETS.c.eksik_fiyat == 0).order_by(S.SETS.c.id).limit(n)).all()
        items = S._items_of(c, [r.id for r in sample])
    for r in sample:
        its = items.get(r.id, [])
        vat = {x["stok"]: float(x["v"] or 0) for x in logo(f"SELECT CODE AS stok, SELLVAT AS v FROM dbo.LG_{cur}_ITEMS WHERE CODE IN ({inlist([i.stok_kodu for i in its])})")}
        tot = sum((i.liste_fiyat or 0) * i.adet for i in its)
        net = sum(r.set_fiyati * ((i.liste_fiyat or 0) * i.adet / tot) / (1 + vat.get(i.stok_kodu, 0) / 100) for i in its) if tot else None
        cost_known = all(i.maliyet is not None for i in its)
        ok = close(r.net_gelir, net) and ((r.marj is None) != cost_known)
        record(f"K7 marj {r.id}", "OK" if ok else "FARK", portal={"netGelir": r.net_gelir, "marj": r.marj, "eksikMaliyet": r.eksik_maliyet},
               referans={"netGelir": net, "maliyetBiliniyor": cost_known, "maliyetKaynagi": st["costSource"]})

    # K8 — yazma yasağı (statik): kaynak katmanında yazan SQL yok
    body = (Path(src.__file__)).read_text(encoding="utf-8").upper()
    bad = [kw for kw in ("INSERT INTO", "UPDATE DBO", "DELETE FROM", "MERGE ", "EXEC ") if kw in body]
    record("K8a CRM/Logo/T-soft'a yazan çağrı yok", "OK" if not bad else "FARK", bulunan=bad)

    if args.api:
        api(engine, tenant, args, n)
    return finish(args)


def olcum(logo, crm, p, cur, end, st, set_codes, n) -> None:
    # Ö1 — set kartlarının Logo kart türü (Karma Koli = 2 var mı?)
    rows = logo(f"SELECT CARDTYPE AS t, COUNT(*) AS n FROM dbo.LG_{cur}_ITEMS WHERE CODE IN ({inlist(set_codes)}) GROUP BY CARDTYPE")
    record("Ö1 set kodlarının Logo kart türü", "ÖLÇÜM", crm_set_kodu=len(set_codes), dagilim={r["t"]: r["n"] for r in rows},
           logoda_yok=len(set_codes) - sum(r["n"] for r in rows))
    # Ö2 — bileşen kaynağı: CRM set işlemi / Logo reçetesi / ikisi
    crm_comp = {r["k"] for r in crm(f"SELECT DISTINCT ps.ProductNumber AS k FROM {p}new_setislemiBase si JOIN {p}ProductBase ps "
                                    f"ON ps.ProductId = si.new_urunid WHERE si.statecode = 0 AND si.new_islemtipi = 1")}
    bom = {r["k"] for r in logo(f"SELECT DISTINCT M.CODE AS k FROM dbo.LG_{cur}_BOMASTER B JOIN dbo.LG_{cur}_ITEMS M "
                                f"ON M.LOGICALREF = B.MAINPRODREF WHERE B.ACTIVE = 0 AND M.CODE IN ({inlist(set_codes)})")}
    sc = set(set_codes)
    record("Ö2 bileşen kaynağı", "ÖLÇÜM", crm_set_islemi=len(sc & crm_comp), logo_recete=len(sc & bom), ikisi=len(sc & crm_comp & bom),
           hicbiri=len(sc - crm_comp - bom))
    lts = logo(f"SELECT L.LINETYPE AS t, COUNT(*) AS n FROM dbo.LG_{cur}_BOMLINE L JOIN dbo.LG_{cur}_BOMASTER B ON B.LOGICALREF = L.BOMMASTERREF "
               f"JOIN dbo.LG_{cur}_ITEMS M ON M.LOGICALREF = B.MAINPRODREF WHERE M.CODE IN ({inlist(set_codes)}) GROUP BY L.LINETYPE")
    record("Ö2b set reçete satır türleri", "ÖLÇÜM", dagilim={r["t"]: r["n"] for r in lts},
           not_="bileşen satır türü belirlenince SETS_BOM_LINETYPES ayarına yazılır")
    # Ö3 — çift sayım: set satırı olan faturada aynı setin bileşeni ayrıca satılmış mı; set faturasında satır türleri
    y = end.year if end else None
    if y:
        f = cur
        inv = logo(f"""SELECT COUNT(DISTINCT S.INVOICEREF) AS v FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE I.CODE IN ({inlist(set_codes)}) AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9) AND S.DATE_ >= '{y}-01-01'""")[0]["v"]
        lt = logo(f"""SELECT X.LINETYPE AS t, COUNT(*) AS n FROM dbo.LG_{f}_01_STLINE X WHERE X.INVOICEREF IN (
  SELECT S.INVOICEREF FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF
  WHERE I.CODE IN ({inlist(set_codes)}) AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9) AND S.DATE_ >= '{y}-01-01')
  AND X.CANCELLED = 0 GROUP BY X.LINETYPE""")
        record(f"Ö3a set içeren fatura ({y}) ve satır türleri", "ÖLÇÜM", fatura=inv, satir_turu={r["t"]: r["n"] for r in lt},
               not_="6/7 (karma koli) varsa SETS_SALES_LINETYPES gözden geçirilir")
        comp = crm(f"""SELECT ps.ProductNumber AS set_kodu, p.ProductNumber AS bilesen FROM {p}new_setislemiBase si
JOIN {p}ProductBase ps ON ps.ProductId = si.new_urunid JOIN {p}new_setislemisatiriBase sl ON sl.new_setislemiid = si.new_setislemiId
JOIN {p}ProductBase p ON p.ProductId = sl.new_urunid WHERE si.statecode = 0 AND si.new_islemtipi = 1 AND sl.new_tip = 2""")
        pairs = sorted({(r["set_kodu"], r["bilesen"]) for r in comp if r["set_kodu"] in sc})
        both = 0
        zero = 0
        for part in range(0, len(pairs), 300):
            chunk = pairs[part:part + 300]
            cond = " OR ".join(f"(I1.CODE = N'{q(a)}' AND I2.CODE = N'{q(b)}')" for a, b in chunk)
            r = logo(f"""SELECT COUNT(DISTINCT S1.INVOICEREF) AS v, SUM(CASE WHEN S2.LINENET = 0 THEN 1 ELSE 0 END) AS z
FROM dbo.LG_{f}_01_STLINE S1 JOIN dbo.LG_{f}_ITEMS I1 ON I1.LOGICALREF = S1.STOCKREF
JOIN dbo.LG_{f}_01_STLINE S2 ON S2.INVOICEREF = S1.INVOICEREF AND S2.LOGICALREF <> S1.LOGICALREF
JOIN dbo.LG_{f}_ITEMS I2 ON I2.LOGICALREF = S2.STOCKREF
WHERE ({cond}) AND S1.CANCELLED = 0 AND S2.CANCELLED = 0 AND S1.INVOICEREF <> 0 AND S1.TRCODE IN (7,8,9) AND S1.DATE_ >= '{y}-01-01'""")[0]
            both += int(r["v"] or 0)
            zero += int(r["z"] or 0)
        record(f"Ö3b aynı faturada set + kendi bileşeni ({y})", "ÖLÇÜM", fatura=both, sifir_tutarli_bilesen_satiri=zero,
               not_="0 ise çift sayım yok (varsayılan doğru); >0 ise satırlar incelenir, sıfır tutarlılar ciroyu şişirmez ama adedi şişirir")
    # Ö4 — B2C siparişlerinin CRM'deki kapsamı: son 24 ay, aylık; tip 8 ile «B2C» adı örtüşmesi
    rows = crm(f"""SELECT FORMAT(s.new_siparistarihi, 'yyyy-MM') AS ay,
  SUM(CASE WHEN s.new_siparistipi = 8 THEN 1 ELSE 0 END) AS tip8, SUM(CASE WHEN LEFT(s.new_name, 3) = N'B2C' THEN 1 ELSE 0 END) AS ad_b2c,
  SUM(CASE WHEN s.new_siparistipi = 8 OR LEFT(s.new_name, 3) = N'B2C' THEN 1 ELSE 0 END) AS b2c
FROM {p}new_siparisBase s WHERE s.statuscode NOT IN (1, 100000001) AND s.new_siparistarihi >= DATEADD(month, -24, GETDATE())
GROUP BY FORMAT(s.new_siparistarihi, 'yyyy-MM') ORDER BY 1""")
    record("Ö4 B2C sipariş kapsamı (aylık)", "ÖLÇÜM", aylar=rows,
           not_="ay boşluğu/ani düşüş T-soft siparişlerinin CRM'e düşmediğini gösterir; e-ticaret sipariş sayısıyla uzmana doğrulatılır")
    # Ö5 — 157 kodları ve kullanım durumu
    rows = logo(f"SELECT ACTIVE AS a, CARDTYPE AS t, COUNT(*) AS n FROM dbo.LG_{cur}_ITEMS WHERE CODE LIKE '{q(st['promoPrefix'])}%' GROUP BY ACTIVE, CARDTYPE")
    record("Ö5 157 kodları", "ÖLÇÜM", dagilim=rows)
    # Ö6 — hediye/promosyon bayraklarının doluluğu (son 24 ay)
    r = crm(f"""SELECT SUM(CASE WHEN s.new_hediyepaketiyapilacak = 1 THEN 1 ELSE 0 END) AS hediye_paketi, COUNT(*) AS siparis
FROM {p}new_siparisBase s WHERE s.new_siparistarihi >= DATEADD(month, -24, GETDATE())""")[0]
    r2 = crm(f"""SELECT SUM(CASE WHEN ss.new_kesinhediye = 1 THEN 1 ELSE 0 END) AS kesin_hediye, SUM(CASE WHEN ss.new_promosyon = 1 THEN 1 ELSE 0 END) AS promosyon,
  SUM(CASE WHEN ss.new_bedelsiz = 1 THEN 1 ELSE 0 END) AS bedelsiz, COUNT(*) AS satir
FROM {p}new_siparissatiriBase ss JOIN {p}new_siparisBase s ON s.new_siparisId = ss.new_siparisid
WHERE s.new_siparistarihi >= DATEADD(month, -24, GETDATE())""")[0]
    record("Ö6 hediye/promosyon bayrakları (24 ay)", "ÖLÇÜM", siparis=r, satir=r2)
    # Ö7 — sepet sorgusunun süresi (uygulamanın kendi sorgusu; yalnız süre ölçülür, sonuç karşılaştırmaya girmez)
    t0 = time.monotonic()
    m = end.year * 12 + end.month - 1 - st["basketMonths"] if end else None
    if m is not None:
        from datetime import date as _d
        pairs, counts, total = src.read_basket(crm, admin_mod.conf("CRM_SCHEMA", "Timas_MSCRM.dbo"), _d(m // 12, m % 12 + 1, 1),
                                               st["b2cTypes"], st["b2cPrefix"], st["basketMinOrders"])
        record("Ö7 sepet sorgusu süresi", "ÖLÇÜM", sn=round(time.monotonic() - t0, 1), cift=len(pairs), siparis=total)


def api(engine, tenant: str, args, n: int) -> None:
    base = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795").rstrip("/")
    cookie = os.environ.get("TIMAS_COOKIE", "")
    if not cookie:
        record("API", "DOĞRULANAMADI", neden="TIMAS_COOKIE yok")
        return

    def call(method: str, path: str, body=None):
        req = urllib.request.Request(base + path, method=method, headers={"cookie": cookie, "Content-Type": "application/json"},
                                     data=None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    code, meta = call("GET", "/api/v1/marketing/sets/meta")
    record("A1 meta", "OK" if code == 200 else "FARK", durum=code, maliyetGorur=(meta or {}).get("me", {}).get("canSeeCost") if code == 200 else None)
    code, lst = call("GET", "/api/v1/marketing/sets?page=0")
    with engine.connect() as c:
        dbn = c.execute(sa.select(sa.func.count()).select_from(S.SETS).where(S.SETS.c.tenant_id == tenant)).scalar()
    record("A2 set listesi (tavansız toplam)", "OK" if code == 200 and lst["total"] == dbn else "FARK", api=lst.get("total") if code == 200 else code, db=dbn)
    code, pr = call("GET", "/api/v1/marketing/promo-items?stok=0")
    with engine.connect() as c:
        dbz = c.execute(sa.select(sa.func.count()).select_from(S.PROMO).where(sa.or_(S.PROMO.c.stok <= 0, S.PROMO.c.stok.is_(None)))).scalar()
    record("A3 stoğu olmayan promosyon ürünü", "OK" if code == 200 and pr["total"] == dbz else "FARK", api=pr.get("total") if code == 200 else code, db=dbz)
    code, sg = call("GET", "/api/v1/marketing/sets/suggestions")
    record("A4 öneriler", "OK" if code == 200 else "FARK", durum=code, toplam=sg.get("total") if code == 200 else None)
    code, _ = call("POST", "/api/v1/marketing/sets", {})
    record("A5 boş gövde 400", "OK" if code == 400 else "FARK", durum=code)
    if not args.yazma:
        return
    ids = {"sets": [], "offers": []}
    with engine.connect() as c:
        comp = [r[0] for r in c.execute(sa.select(S.BOOKS.c.stok_kodu).where(S.BOOKS.c.crm_tip == 1, S.BOOKS.c.stok > 0)
                                        .order_by(S.BOOKS.c.son12_adet.desc()).limit(2)).all()]
    code, s = call("POST", "/api/v1/marketing/sets", {"ad": "KABUL TESTİ set", "tur": "tematik", "setFiyati": 100,
                                                      "bilesenler": [{"stok": c_, "adet": 1} for c_ in comp]})
    if code != 201:
        record("Y1 taslak set", "FARK", durum=code, cevap=s)
        return
    ids["sets"].append(s["id"])
    Path(args.ids).write_text(json.dumps(ids))
    code, pc = call("POST", f"/api/v1/marketing/sets/{s['id']}/price", {"indirim": 0.2})
    record("Y2 fiyat hesabı (kaydetmeden)", "OK" if code == 200 and pc.get("listeToplami") else "FARK", durum=code,
           marjMesaj=(pc or {}).get("marjMesaj") if code == 200 else None)
    code, _ = call("POST", f"/api/v1/marketing/sets/{s['id']}/submit")
    code2, e = call("POST", f"/api/v1/marketing/sets/{s['id']}/approve", {})
    record("Y3 gönderen onaylayamaz", "OK" if code == 200 and code2 in (403, 409) else "FARK", gonder=code, onay=code2, cevap=e)
    call("POST", f"/api/v1/marketing/sets/{s['id']}/withdraw")
    code, _ = call("DELETE", f"/api/v1/marketing/sets/{s['id']}")
    record("Y4 taslak silindi", "OK" if code == 200 else "FARK", durum=code)
    banned = re.compile(r"qwen|vllm|temporal|timesfm|ollama|openai|gpt|llama", re.I)
    record("Y5 ekrana giden metinde teknoloji adı yok", "OK" if not banned.search(json.dumps(meta, ensure_ascii=False)) else "FARK")


def finish(args) -> int:
    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
    bad = [r for r in RESULTS if r["durum"] == "FARK"]
    unv = [r for r in RESULTS if r["durum"] == "DOĞRULANAMADI"]
    print(f"\nToplam {len(RESULTS)} · FARK {len(bad)} · DOĞRULANAMADI {len(unv)} · sonuç {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
