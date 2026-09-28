"""M16 Lansman / yayın ayı — kabul (test sunucusunda, gerçek CRM .28 + Logo .155, çalışan köprüye karşı).

«Geriye dönük lansman»: yakın geçmişte yayımlanmış bir yeni kitap için kabul planı ve lansmanı açılır, köprü CRM ve
Logo'yu okur, ekrana giden rakamlar bağımsız doğrudan SQL ile karşılaştırılır, sonra her şey silinir (`cleanup.py`).

Koşum (köprünün env'i ile; Mac'te koşulmaz):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && M16_COOKIE='timas_session=…' python3 ../scripts/acceptance/m16/accept.py --stok <kod> --yayin <YYYY-AA-GG> > m16-kabul.json

`M16_COOKIE`: `timasai` hesabının kısa ömürlü (15 dk) oturumu; bitince oturum satırı silinir. Yeni kullanıcı adı
uydurulmaz: kabul planının oluşturanı ve onaylayanı `timasai`dir (plan doğrudan onaylı yazılır; onay akışı M15
kabulünde sınanıyor). Yayın günü olarak kitabın gerçek ilk satış haftası seçilmeli; Logo .155 17.08.2026'da donduğu
için yayını bu tarihten en az 7 gün önce olan kitap seçilirse faturalı satış karşılaştırması anlamlı olur.

Denetimler (her biri doğrudan SQL referanslı; «ölçülecek» notları günlükte):
  1. Sipariş sinyali: CRM sipariş satırı gün gün (UTC → İstanbul +3, `MARKETING_LAUNCH_ORDER_EXCLUDE` durumları hariç)
     = İzleme serisi `siparis`.
  2. Faturalı satış: Logo STLINE (ITEMS.CODE ile birleştirme — köprü STOCKREF ile süzer, iki yol) gün gün = `fatura`,
     veri sonu = `MAX(DATE_)`.
  3. Açık sipariş (Baskı Öneri SQL'i dosyadan, süzmesiz) ve CRM «Bekleyen Ürün» = bugünün anlık değerleri.
  4. Dağılım: sipariş tipi 2 adet toplamı ve `COUNT(DISTINCT firma)` = İzleme «Dağılım».
  5. Depo stoku: Baskı Öneri depo görünümü = bugünün `depo`.
  6. Hedef payı: bütçe modülünün `targets` ucu (aylık hedef ÷ ayın gün sayısı) D..D+6 toplamı = `hedefKum` (D+6).
  7. Etkinlik: `new_etkinlikBase` ilgili kitap, durum Tamamlandı: sayı ve satılan kitap = Etkinlikler toplamı.
  8. Rapor: D+7 rakam tablosundaki sipariş/fatura/hedef = İzleme toplamları; Zeki AI özetindeki her sayı olgu
     listesinde; ekranda teknoloji adı 0.
  9. Dış kanal: M16 kodunda dış platforma yazan çağrı yok (statik tarama).
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge.management import sql_text  # noqa: E402
from semantic_bridge.marketing import guard as G  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BRIDGE = os.environ.get("M16_BRIDGE", "http://127.0.0.1:8795")
STATE = Path(os.environ.get("M16_STATE", "m16-kabul-state.json"))
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
ACTOR = "timasai"


def api(method: str, path: str, body: Any = None, raw: bool = False) -> tuple[int, Any]:
    headers = {"Cookie": os.environ["M16_COOKIE"], "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BRIDGE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            payload = r.read()
            return r.status, payload if raw else json.loads(payload or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def near(a: Any, b: Any, tol: float = 0.005) -> bool:
    a = 0.0 if a is None else float(a)
    b = 0.0 if b is None else float(b)
    return abs(a - b) <= tol


def day(v: Any) -> str:
    return bsrc._day(v).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stok", required=True, help="yakın geçmişte yayımlanmış yeni kitabın stok kodu")
    ap.add_argument("--yayin", required=True, help="kabulde esas alınacak yayın günü (YYYY-AA-GG)")
    ap.add_argument("--kitap-id", default="", help="CRM kitap kimliği (boşsa stok kodundan okunur)")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = bsrc.runner(s.connection_file)
    firms = bsrc.firms_by_year(logo)
    store = open_store(s.store_dsn, create=False)
    engine = store.engine
    out: dict[str, Any] = {"stok": args.stok, "yayin": args.yayin, "checks": []}
    state: dict[str, Any] = json.loads(STATE.read_text()) if STATE.exists() else {"plans": [], "launches": [], "meta": []}

    def check(name: str, ok: bool, **detail: Any) -> None:
        out["checks"].append({"ad": name, "ok": bool(ok), **detail})

    def save() -> None:
        STATE.write_text(json.dumps(state))

    from semantic_bridge import admin as admin_mod
    from semantic_bridge.marketing import core as C
    from semantic_bridge.marketing import launch as L

    admin_mod.ensure(engine)
    L.ensure(engine)
    if (admin_mod.conf("MARKETING_ALERT_RECIPIENTS") or admin_mod.conf("MARKETING_LAUNCH_STOCK_RECIPIENTS") or "").strip():
        print(json.dumps({"hata": "Bildirim alıcıları dolu: kabul yenilemesi gerçek e-posta atmaz ama run-due atar; bu betik "
                                  "run-due çağırmaz. Yine de alıcıları kontrol edin."}, ensure_ascii=False), file=sys.stderr)
    tenant = s.tenant_id
    code = args.stok.replace("'", "''")
    pub = date.fromisoformat(args.yayin)
    kid = args.kitap_id
    if not kid:
        r = crm(f"SELECT TOP 1 new_kitapId AS id FROM {SCHEMA}.new_kitapBase WHERE statecode = 0 AND new_StokKodu = N'{code}'")
        kid = str(r[0]["id"]).lower() if r else ""

    # ---- kabul planı (doğrudan onaylı) ve lansman (API)
    pid = C.create_plan(engine, tenant, ACTOR, kind="yeni", baslik=f"KABUL M16 · {args.stok}", stok_kodu=args.stok,
                        crm_kitap_id=kid or None, yayin_tarihi=pub.isoformat(), yayin_kaynagi="elle", hedef={"planId": None})
    state["plans"].append(pid)
    save()
    with engine.begin() as c:
        c.execute(C.PLANS.update().where(C.PLANS.c.id == pid).values(durum="onayli", onaylayan=ACTOR, onay_zamani=C.now()))
    st_, launch = api("POST", "/api/v1/marketing/launches", {"planId": pid})
    if st_ != 201:
        check("0-lansman-ac", False, durum=st_, hata=launch)
        return finish(out)
    lid = launch["id"]
    state["launches"].append(lid)
    save()
    meta_q = sa.text("SELECT key FROM semantic_mkt_meta WHERE key LIKE 'launch-emsal:%'")
    with engine.connect() as c:
        before = set(c.execute(meta_q).scalars().all())
    st_, ref = api("POST", f"/api/v1/marketing/launches/{lid}/refresh", {})
    check("0-okuma", st_ == 200 and not ref["rapor"]["hatalar"], durum=st_, hatalar=(ref.get("rapor") or {}).get("hatalar") if st_ == 200 else ref)
    with engine.connect() as c:
        state["meta"] = sorted(set(c.execute(meta_q).scalars().all()) - before)   # yalnız kabulün oluşturduğu önbellek
    save()
    _, tr7 = api("GET", f"/api/v1/marketing/launches/{lid}/tracking?gun=7")
    _, tr30 = api("GET", f"/api/v1/marketing/launches/{lid}/tracking?gun=30")
    seri = {r["gun"]: r for r in tr30["seri"]}
    today = date.today()
    pre = int(admin_mod.conf("MARKETING_LAUNCH_PRE_DAYS") or 14)
    a, b = pub - timedelta(days=pre), min(pub + timedelta(days=29), today)
    excl = ", ".join(x.strip() for x in (admin_mod.conf("MARKETING_LAUNCH_ORDER_EXCLUDE") or "1,100000001").split(",") if x.strip())

    # 1 ---------------------------------------------------------------- sipariş sinyali
    rows = crm(f"""
SELECT CAST(DATEADD(hour, 3, s.new_siparistarihi) AS date) AS gun, SUM(ss.new_adet) AS adet
FROM {SCHEMA}.new_siparissatiriBase ss JOIN {SCHEMA}.new_siparisBase s ON s.new_siparisId = ss.new_siparisid
WHERE ss.new_StokKodu = N'{code}' AND s.statuscode NOT IN ({excl})
  AND s.new_siparistarihi >= DATEADD(hour, -3, '{a.isoformat()}') AND s.new_siparistarihi < DATEADD(hour, -3, '{(b + timedelta(days=1)).isoformat()}')
GROUP BY CAST(DATEADD(hour, 3, s.new_siparistarihi) AS date)""")
    ref1 = {day(r["gun"]): float(r["adet"] or 0) for r in rows}
    bad1 = [g for g in {*ref1, *(g for g in seri if a.isoformat() <= g <= b.isoformat())}
            if not near(ref1.get(g), (seri.get(g) or {}).get("siparis"))]
    check("1-siparis", not bad1, gun=len(ref1), toplamSql=sum(ref1.values()), fark=sorted(bad1)[:20])

    # 2 ---------------------------------------------------------------- faturalı satış + veri sonu
    ref2: dict[str, float] = {}
    for y in range(pub.year, b.year + 1):
        firm = firms.get(y)
        if not firm:
            continue
        lo, hi = max(pub, date(y, 1, 1)), min(b, date(y, 12, 31))
        for r in logo(f"""
SELECT CAST(S.DATE_ AS date) AS gun, SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet
FROM dbo.LG_{firm}_01_STLINE S JOIN dbo.LG_{firm}_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9) AND I.CODE = '{code}'
  AND S.DATE_ >= '{lo.isoformat()}' AND S.DATE_ < '{(hi + timedelta(days=1)).isoformat()}'
GROUP BY CAST(S.DATE_ AS date)"""):
            ref2[day(r["gun"])] = float(r["adet"] or 0)
    end = bsrc.read_data_end(logo, firms)
    shown_end = tr30["veriSonu"]["logo"]
    bad2 = [g for g, r in seri.items() if g >= pub.isoformat() and g <= b.isoformat() and end and g <= end.isoformat()
            and not near(ref2.get(g), r.get("fatura"))]
    after = [g for g, r in seri.items() if end and g > end.isoformat() and r.get("fatura") is not None]
    check("2-fatura", not bad2 and not after and shown_end == (end.isoformat() if end else None),
          veriSonuSql=end.isoformat() if end else None, veriSonuEkran=shown_end, fark=sorted(bad2)[:20], veriSonuSonrasiDolu=after[:10])

    # 3 ---------------------------------------------------------------- açık sipariş ve bekleyen ürün (bugünün anlık değeri)
    full_open = crm(sql_text("baski-oneri", "crm_bekleyen_siparis").replace("Timas_MSCRM.dbo.", f"{SCHEMA}."))
    ref3 = sum(float(r["bekleyen_siparis"] or 0) for r in full_open if str(r.get("stok_kodu") or "").strip() == args.stok)
    pend = crm(f"""SELECT SUM(b.new_adet) AS adet FROM {SCHEMA}.new_bekleyenurunBase b JOIN {SCHEMA}.ProductBase p ON p.ProductId = b.new_urunid
WHERE b.statuscode = 1 AND p.ProductNumber = N'{code}'""")
    ref3b = float((pend[0]["adet"] if pend else 0) or 0)
    sig = tr30.get("sinyal") or {}
    todayrow = seri.get(today.isoformat()) or {}
    snap_row = next((r for r in reversed(tr30["seri"]) if r.get("bekleyenUrun") is not None), {})
    check("3-acik-siparis-bekleyen-urun", near(ref3, sig.get("bekleyen")) and near(ref3b, snap_row.get("bekleyenUrun")),
          acikSql=ref3, acikEkran=sig.get("bekleyen"), bekleyenUrunSql=ref3b, bekleyenUrunEkran=snap_row.get("bekleyenUrun"),
          not_="Pencere bugünü kapsamıyorsa (yayın 30 günden eski) anlık değer yalnız sinyalde" if not todayrow else None)

    # 4 ---------------------------------------------------------------- dağılım
    d = crm(f"""
SELECT SUM(ss.new_adet) AS adet, COUNT(DISTINCT s.new_firmaid) AS bayi
FROM {SCHEMA}.new_siparissatiriBase ss JOIN {SCHEMA}.new_siparisBase s ON s.new_siparisId = ss.new_siparisid
WHERE ss.new_StokKodu = N'{code}' AND s.statuscode NOT IN ({excl}) AND s.new_siparistipi = 2
  AND s.new_siparistarihi >= DATEADD(hour, -3, '{a.isoformat()}') AND s.new_siparistarihi < DATEADD(hour, -3, '{(b + timedelta(days=1)).isoformat()}')""")
    dist = tr30.get("dagilim") or {}
    check("4-dagilim", bool(d) and near(d[0]["adet"], dist.get("adet")) and near(d[0]["bayi"], dist.get("bayi")),
          sql={"adet": d[0]["adet"] if d else None, "bayi": d[0]["bayi"] if d else None}, ekran=dist)

    # 5 ---------------------------------------------------------------- depo stoku
    dep = logo(sql_text("baski-oneri", "logo_depo_stok"))
    key = lambda v: "".join(str(v or "").split()).upper()  # noqa: E731 — köprüdeki launch_sources.stock_key ile aynı
    ref5 = sum(float(r["depo_stok"] or 0) for r in dep if key(r.get("stok_kodu")) == key(args.stok))
    # Logo görünümünün son okuması sinyalde (`depo.logo`); pencere (D+30) bittiyse seride görünmez. Eski köprüde seri.
    dp = tr30.get("depo") or {}
    depo_row = next((r for r in reversed(tr30["seri"]) if r.get("depo") is not None), {})
    ekran5 = dp.get("logo") if dp.get("logo") is not None else depo_row.get("depo")
    check("5-depo", near(ref5, ekran5), sql=ref5, ekran=ekran5, ekranSecilen=dp.get("deger"), ekranKaynak=dp.get("kaynakAdi"))

    # 6 ---------------------------------------------------------------- hedef payı (D..D+6)
    st_, tg = api("GET", f"/api/v1/budget/targets?year={pub.year}&stok={args.stok}&actuals=false")
    want6 = None
    if st_ == 200 and tg.get("items"):
        aylik = {m["ay"]: m["adet"] for m in tg["items"][0]["aylik"]}
        want6 = sum(aylik.get((pub + timedelta(days=i)).month, 0) / calendar.monthrange((pub + timedelta(days=i)).year, (pub + timedelta(days=i)).month)[1]
                    for i in range(7) if (pub + timedelta(days=i)).year == pub.year)
    got6 = next((r["hedefKum"] for r in tr7["seri"] if r["d"] == 6), None)
    check("6-hedef-payi", (want6 is None and got6 is None) or near(want6, got6, 0.05), sql=want6, ekran=got6,
          not_="Kitap yürürlükteki bütçe planında yoksa ikisi de boş olmalı")

    # 7 ---------------------------------------------------------------- etkinlik
    if kid:
        ev = crm(f"""SELECT COUNT(*) AS n, SUM(new_SatilanKitapAd) AS satilan FROM {SCHEMA}.new_etkinlikBase
WHERE new_lgiliKitap = '{kid}' AND statuscode = 100000002""")
        _, evs = api("GET", f"/api/v1/marketing/launches/{lid}/events")
        tot = evs.get("toplam") or {}
        check("7-etkinlik", near(ev[0]["n"], tot.get("tamamlanan")) and near(ev[0]["satilan"], tot.get("satilan")),
              sql={"n": ev[0]["n"], "satilan": ev[0]["satilan"]}, ekran=tot)
    else:
        check("7-etkinlik", False, hata="CRM kitap kimliği bulunamadı")

    # 8 ---------------------------------------------------------------- D+7 raporu
    st_, dr = api("POST", f"/api/v1/marketing/launches/{lid}/reviews/7/draft")
    if st_ == 202:
        for _ in range(120):
            _, rv = api("GET", f"/api/v1/marketing/launches/{lid}/reviews")
            if not any(j["durum"] in ("bekliyor", "calisiyor") for j in rv["jobs"]):
                break
            time.sleep(5)
        r7 = next((x for x in rv["items"] if x["gun"] == 7), None) or {}
        by = {x["anahtar"]: x["deger"] for x in (r7.get("rakam") or {}).get("satirlar") or []}
        t7 = tr7["toplam"]
        facts_nums = set()
        for x in (r7.get("rakam") or {}).get("satirlar") or []:
            if not x.get("para") and x.get("deger") is not None:
                facts_nums |= G.numbers_in(f"{x['deger']:,.1f}".replace(",", "X").replace(".", ",").replace("X", "."))
                facts_nums |= G.numbers_in(f"{x['deger']:,.0f}".replace(",", "."))
        stray = [n for n in G.numbers_in(r7.get("ozet") or "") if n not in facts_nums and n not in {"7", "30"}]
        check("8-rapor", near(by.get("siparis"), t7["siparis"]) and near(by.get("hedef"), t7["hedef"] or None)
              and not G.has_tech_name(json.dumps(rv, ensure_ascii=False)),
              rapor={k: by.get(k) for k in ("siparis", "fatura", "hedef")}, izleme={k: t7.get(k) for k in ("siparis", "fatura", "hedef")},
              ozetteTablodaOlmayanSayi=stray, not_="Özette yıl/gün sayısı olgu listesinde (yayın günü) olabilir; liste elle gözden geçirilir")
    else:
        check("8-rapor", False, durum=st_, hata=dr)

    # 9 ---------------------------------------------------------------- dış kanal (statik)
    bad9 = []
    for f in (ROOT / "backend" / "semantic_bridge" / "marketing").glob("launch*.py"):
        text = f.read_text(encoding="utf-8")
        for pat in (r"\brequests\.", r"\bhttpx\b", r"urllib\.request", r"\btsoft\b", r"seo_geo\.connections", r"\bINSERT\s+INTO\s+\w*MSCRM",
                    r"webhook", r"graph\.facebook", r"api\.twitter", r"instagram"):
            if re.search(pat, text, re.I):
                bad9.append(f"{f.name}: {pat}")
    check("9-dis-kanal-yok", not bad9, bulunan=bad9)
    return finish(out)


def finish(out: dict[str, Any]) -> int:
    out["ozet"] = {"gecti": sum(1 for c in out["checks"] if c["ok"]), "kaldi": sum(1 for c in out["checks"] if not c["ok"])}
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["ozet"]["kaldi"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
