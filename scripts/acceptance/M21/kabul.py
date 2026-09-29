"""M21 Dijital pazarlama ve reklam — kabul (test sunucusunda, gerçek Logo .25 + CRM .28, çalışan köprüye karşı).

Koşum (test sunucusu, köprünün env'i ile; Mac'te koşulmaz):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && M21_COOKIE='timas_session=…' python3 ../scripts/acceptance/M21/kabul.py [--stok <kitap stok kodu>] [--write] \
         [--bas 2026-07-19 --bit 2026-08-17] > m21-kabul.json

`M21_COOKIE`: `timasai` hesabının kısa ömürlü (15 dk) portal oturumu; kabul bitince oturum satırı silinir. Yeni kullanıcı
adı uydurulmaz. `--write` kabul için geçici bir reklam hesabı açar, yapay (günlük 3 satırlık) harcama dosyası yükler,
kampanyayı `--stok` kitabına bağlar; kimlikler durum dosyasına yazılır ve `cleanup.py` hepsini siler.

Denetimler — uygulamanın ekrana verdiği sonuç, bağımsız doğrudan SQL referansıyla karşılaştırılır (kuruş payı 0,01):
  1. E-ticaret net cirosu (dönem, veri sonuna kadar): `GET /overview` göstergesi = STLINE ⨝ CLCARD (SPECODE2 kanal
     kodları, faturalı, TRCODE 7/8/9 − 2/3, LINENET). Güncel yıl ve bir önceki yıl dönemi (211 firması) ayrı ayrı.
  2. Kitap bazlı ciro (--write): bağlı kitabın e-ticaret ve toplam net cirosu = STLINE doğrudan; `V_SatisRaporu_411`
     toplamı ikinci referans olarak raporlanır (görünüm satış tanımı farklı olabilir; fark yazılır, başarı ölçütü STLINE).
  3. İçe aktarma (--write): dosyanın harcama toplamı = `SUM(spend) FROM semantic_ads_daily WHERE import_id` = API toplamı.
  4. CRM bütçe: `GET /crm` bütçe kaydı toplamı = `SUM(COALESCE(new_tutar_Base, new_tutar))` aynı UTC sınırlarıyla.
  5. Reklam planı: ekrandaki etkin plan sayısı = `COUNT(*) FROM new_reklamplaniBase WHERE statecode = 0` (C20'de 68).
  6. Stok (--write): bağlı kitabın stok bakiyesi = güncel kopyada «stok bakiyesi» ölçüsü (IOCODE 1/2 − 3/4, tarihsiz).
  7. Veri sınırı: ekrandaki «satış verisi şu güne kadar» = STLINE faturalı satış MAX(DATE_); `V_SatisRaporu_411` en son
     fatura tarihi ikinci referans olarak yazılır.
  8. Teknoloji adı: özet, kampanya ve öneri cevaplarında model/altyapı adı 0.
Çıktı: JSON; her denetimde `ok`; sonda özet.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import ads_sources as S  # noqa: E402
from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge.marketing import guard as G  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BRIDGE = os.environ.get("M21_BRIDGE", "http://127.0.0.1:8795")
STATE = Path(os.environ.get("M21_STATE", "m21-kabul-state.json"))
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")
TOL = 0.01


def api(method: str, path: str, body: Any = None) -> tuple[int, Any]:
    headers = {"Cookie": os.environ["M21_COOKIE"], "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BRIDGE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=1800) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def near(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= TOL


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stok", help="--write için bağlanacak kitabın stok kodu (e-ticarette satışı olan bir kitap seçin)")
    ap.add_argument("--bas", help="dönem başı (varsayılan: veri sonundan 29 gün önce)")
    ap.add_argument("--bit", help="dönem sonu (varsayılan: Logo veri sonu)")
    ap.add_argument("--write", action="store_true", help="geçici hesap + yapay dosya + kitap bağı; cleanup.py siler")
    ap.add_argument("--refresh", action="store_true", help="önce satış önbelleğini yenile (POST /refresh) ve bitmesini bekle")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    logo = bsrc.runner(s.connection_file)
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    firms = bsrc.firms_by_year(logo)
    store = open_store(s.store_dsn, create=False)
    out: dict[str, Any] = {"checks": [], "firmalar": firms}
    state: dict[str, Any] = json.loads(STATE.read_text()) if STATE.exists() else {}

    def check(name: str, ok: bool, **detail: Any) -> None:
        out["checks"].append({"ad": name, "ok": bool(ok), **detail})

    def save_state() -> None:
        STATE.write_text(json.dumps(state, ensure_ascii=False))

    st, meta = api("GET", "/api/v1/ads/meta")
    if st != 200:
        print(json.dumps({"hata": f"meta {st}: {meta}"}, ensure_ascii=False))
        return 2
    state.setdefault("baslangic", time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))
    state["kim"] = meta["me"]["username"]
    save_state()
    channels = meta["settings"]["ecomChannels"]
    ch_sql = ", ".join("N'" + c.replace("'", "''") + "'" for c in channels)

    def wait_refresh() -> None:
        st_, r = api("POST", "/api/v1/ads/refresh", {})
        out["yenileme"] = r
        for _ in range(180):
            time.sleep(10)
            _, stt = api("GET", "/api/v1/ads/status")
            if (stt.get("refresh") or {}).get("durum") in ("bitti", "hata"):
                out["yenilemeSonuc"] = stt.get("refresh")
                return

    if args.refresh:
        wait_refresh()
        _, meta = api("GET", "/api/v1/ads/meta")

    # 7 ---------------------------------------------------------------- veri sınırı
    end_ui = (meta.get("logo") or {}).get("veriSonu")
    last = firms[max(firms)]
    ref_end = bsrc._day(logo(bsrc.data_end_sql(last))[0]["son"])
    view_end = None
    try:
        view_end = str(logo("SELECT TOP 1 [Fatura Tarihi] AS t FROM dbo.V_SatisRaporu_411 ORDER BY [Fatura Tarihi] DESC")[0]["t"])[:10]
    except bsrc.SourceError as e:
        view_end = f"okunamadı: {e}"
    check("7-veri-siniri", end_ui == (ref_end.isoformat() if ref_end else None), ekran=end_ui, stline=ref_end and ref_end.isoformat(),
          gorunum=view_end)
    if not end_ui:
        print(json.dumps({**out, "hata": "Logo önbelleği boş; --refresh ile koşun."}, ensure_ascii=False, indent=1))
        return 1
    end = date.fromisoformat(end_ui)

    # 1 ---------------------------------------------------------------- e-ticaret net cirosu
    def ecom_ref(a: date, b: date) -> float:
        total = 0.0
        for y in range(a.year, b.year + 1):
            f = firms.get(y)
            if not f:
                continue
            lo, hi = max(a, date(y, 1, 1)), min(b, date(y, 12, 31))
            r = logo(f"""
SELECT SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.LINENET WHEN s.TRCODE IN (2,3) THEN -s.LINENET END) AS ciro
FROM dbo.LG_{f}_01_STLINE s JOIN dbo.LG_{f}_CLCARD c ON c.LOGICALREF = s.CLIENTREF
WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND c.SPECODE2 IN ({ch_sql})
  AND s.DATE_ >= '{lo.isoformat()}' AND s.DATE_ < '{(hi + timedelta(days=1)).isoformat()}'""")
            total += float(r[0]["ciro"] or 0)
        return round(total, 2)

    bit = date.fromisoformat(args.bit) if args.bit else end
    bas = date.fromisoformat(args.bas) if args.bas else bit - timedelta(days=29)
    # ikinci dönem bir yıl önce (önceki yılın firması); önbellek penceresinin (ADS_LOOKBACK_DAYS=400) içinde kalır
    periods = [(bas, bit), (bit - timedelta(days=365 + 29), bit - timedelta(days=365))]
    for a, b in periods:
        st_, ov = api("GET", f"/api/v1/ads/overview?frm={a}&to={b}")
        if st_ != 200:
            check(f"1-eticaret-{a.year}", False, hata=ov)
            continue
        ref = ecom_ref(a, min(b, end))
        check(f"1-eticaret-{a.year}", near(ov["gosterge"]["eticaretCiro"], ref), ekran=ov["gosterge"]["eticaretCiro"], referans=ref,
              donem=[a.isoformat(), b.isoformat()], verimDonemi=ov.get("verimDonemi"))
        texts = json.dumps(ov, ensure_ascii=False)
        check(f"8-teknoloji-adi-{a.year}", not G.has_tech_name(texts))

    # 4, 5 ------------------------------------------------------------- CRM
    st_, cr = api("GET", f"/api/v1/ads/crm?frm={bas}&to={bit}&yenile=1")
    if st_ != 200:
        check("4-crm-butce", False, hata=cr)
        check("5-reklam-plani", False, hata=cr)
    else:
        lo, hi = cr["donem"]["crmBas"], cr["donem"]["crmBit"]
        r = crm(f"""
SELECT SUM(COALESCE(new_tutar_Base, new_tutar)) AS t, SUM(new_tutar) AS ham, COUNT(*) AS n
FROM {SCHEMA}.new_pazarlamamoduluBase
WHERE statecode = 0 AND new_baslangictarihi < '{hi}' AND new_bitistarihi >= '{lo}'""")[0]
        check("4-crm-butce", near(cr["butceKayitlari"]["toplam"], round(float(r["t"] or 0), 2)), ekran=cr["butceKayitlari"]["toplam"],
              referans=float(r["t"] or 0), hamTutar=float(r["ham"] or 0), kayit=[len(cr["butceKayitlari"]["items"]), r["n"]], sinir=[lo, hi])
        n = crm(f"SELECT COUNT(*) AS n FROM {SCHEMA}.new_reklamplaniBase WHERE statecode = 0")[0]["n"]
        check("5-reklam-plani", cr["reklamPlanlari"]["toplam"] == n, ekran=cr["reklamPlanlari"]["toplam"], referans=n,
              onaysiz=cr["reklamPlanlari"]["onaysiz"])

    # 2, 3, 6 ---------------------------------------------------------- yazma turu
    if args.write:
        if not args.stok:
            check("2-kitap", False, hata="--write için --stok gerekli")
        else:
            stok = args.stok.strip()
            code = stok.replace("'", "''")
            st_, acc = api("POST", "/api/v1/ads/accounts", {"platform": "diger", "ad": f"KABUL M21 {int(time.time())}"})
            if st_ != 201:
                check("3-ice-aktarma", False, hata=acc)
            else:
                state.setdefault("accounts", []).append(acc["id"])
                save_state()
                days = [end - timedelta(days=i) for i in (2, 1, 0)]
                spends = [123.45, 67.89, 10.01]
                csv_ = "Gün;Kampanya;Maliyet\n" + "".join(f"{d.isoformat()};KABUL M21 {stok};{str(v).replace('.', ',')}\n" for d, v in zip(days, spends))
                body = {"dosyaAdi": "kabul-m21.csv", "icerik": base64.b64encode(csv_.encode()).decode(), "hesapId": acc["id"],
                        "eslem": {"day": "Gün", "campaign": "Kampanya", "spend": "Maliyet"}, "baslikSatiri": 1}
                st_, imp = api("POST", "/api/v1/ads/imports", body)
                if st_ != 201:
                    check("3-ice-aktarma", False, hata=imp)
                else:
                    state.setdefault("imports", []).append(imp["id"])
                    save_state()
                    with store.engine.connect() as c:
                        db = c.execute(sa.text("SELECT SUM(spend) FROM semantic_ads_daily WHERE import_id = :i"), {"i": imp["id"]}).scalar()
                    check("3-ice-aktarma", near(db, sum(spends)) and near(imp["toplamHarcama"], sum(spends)),
                          dosya=round(sum(spends), 2), veritabani=db, api=imp["toplamHarcama"])
                    _, camps = api("GET", f"/api/v1/ads/campaigns?frm={days[0]}&to={days[-1]}&q=" + urllib.parse.quote("KABUL M21"))
                    camp = next((c for c in camps.get("items", []) if c["hesapId"] == acc["id"]), None)
                    state.setdefault("campaigns", []).append(camp["id"] if camp else None)
                    save_state()
                    st_, linked = api("PATCH", f"/api/v1/ads/campaigns/{camp['id']}", {"stokKodu": stok}) if camp else (0, "kampanya yok")
                    if st_ != 200:
                        check("2-kitap", False, hata=linked)
                    else:
                        # bağdan sonra kitap önbelleği arka planda tazelenir; bitmesini bekle
                        for _ in range(60):
                            time.sleep(5)
                            _, ov = api("GET", f"/api/v1/ads/overview?frm={days[0]}&to={days[-1]}")
                            book = next((k for k in ov.get("kitaplar", []) if k["stokKodu"] == stok), None)
                            if book and book.get("satis") is not None and book.get("stok") is not None:
                                break
                        f = firms[end.year]
                        r = logo(f"""
SELECT SUM(CASE WHEN c.SPECODE2 IN ({ch_sql}) THEN (CASE WHEN s.TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * s.LINENET ELSE 0 END) AS e,
       SUM((CASE WHEN s.TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * s.LINENET) AS t
FROM dbo.LG_{f}_01_STLINE s JOIN dbo.LG_{f}_ITEMS i ON i.LOGICALREF = s.STOCKREF LEFT JOIN dbo.LG_{f}_CLCARD c ON c.LOGICALREF = s.CLIENTREF
WHERE s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0 AND s.TRCODE IN (2,3,7,8,9) AND i.CODE = N'{code}'
  AND s.DATE_ >= '{days[0].isoformat()}' AND s.DATE_ < '{(days[-1] + timedelta(days=1)).isoformat()}'""")[0]
                        view = None
                        try:
                            ym = [d.year * 12 + d.month for d in (days[0], days[-1])]
                            v = logo(f"""SELECT SUM([Net Tutar]) AS t FROM dbo.V_SatisRaporu_411
WHERE [Malzeme/Hizmet Kodu] = N'{code}' AND [Yıl]*12+[Ay] BETWEEN {ym[0]} AND {ym[1]} AND [Satır Türü] = N'Malzeme'""")
                            view = float(v[0]["t"] or 0)
                        except bsrc.SourceError as e:
                            view = f"okunamadı: {e}"
                        sat = (book or {}).get("satis") or {}
                        check("2-kitap-ciro", book is not None and near(sat.get("eticaretCiro"), round(float(r["e"] or 0), 2))
                              and near(sat.get("toplamCiro"), round(float(r["t"] or 0), 2)),
                              ekran=sat, stlineEticaret=float(r["e"] or 0), stlineToplam=float(r["t"] or 0),
                              gorunumAyToplami=view, not_="görünüm ay bazında; ekran gün bazında — yalnız bilgi")
                        stock_ref = S.stock_sql(firms[max(firms)], [stok])
                        rs = logo(stock_ref)
                        ref_b = float(rs[0]["bakiye"]) if rs else None
                        ui_b = ((book or {}).get("stok") or {}).get("bakiye")
                        check("6-stok", near(ui_b, ref_b), ekran=ui_b, referans=ref_b)
                        state.setdefault("codes", []).append(stok)
                        save_state()

    oks = [c["ok"] for c in out["checks"]]
    out["ozet"] = {"basarili": sum(oks), "basarisiz": len(oks) - sum(oks), "toplam": len(oks)}
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return 0 if all(oks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
