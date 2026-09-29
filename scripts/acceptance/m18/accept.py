"""M18 Aylık pazarlama planı ve satış föyü — kabul (test sunucusunda, gerçek CRM .28 + Logo .25, çalışan köprüye karşı).

Koşum (test sunucusu, köprünün env'i ile; Mac'te koşulmaz):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && M18_COOKIE='timas_session=…' python3 ../scripts/acceptance/m18/accept.py --ay 2026-11 [--write] > m18-kabul.json

`M18_COOKIE`: `timasai` hesabının kısa ömürlü (15 dk) portal oturumu (kullanıcı belleği «test-login-as-timasai»); kabul
bitince oturum satırı silinir. Kabulün oluşturduğu ay planı ve föy satırları `m18-kabul-state.json`'a yazılır,
`cleanup.py` siler (kabulden önce var olan plan ve föylere dokunulmaz).

Denetimler — uygulamanın verdiği sonuç, bağımsız doğrudan SQL referansıyla:
  1. Ayın yeni kitapları: CRM `new_kitapBase` etkin «Kitap», ilk baskı tarihi (UTC saklanır → İstanbul günü) ayın içinde
     = takvimde kaynağı kitap kartı olan «yeni» kalemler = föy listesindeki bu kitaplar (küme birebir).
  2. Aylık hedef payı: `GET /api/v1/budget/targets?year=Y&segment=yeni|backlist` → Σ items[].aylik[ay].ciro = ay
     ekranındaki segment hedefi (kuruşu kuruşuna).
  3. Önceki ay gerçekleşen: Logo `STLINE` faturalı satır (TRCODE 7/8/9 − 2/3, LINENET, 157 hariç) önceki ay = ekrandaki
     şirket gerçekleşeni; veri sonu `MAX(DATE_)` ile aynı.
  4. Föy alanları: 5 kitapta CRM `new_ean13`, `new_kdvdahilfiyat`, `new_TantmFyMetni`, `new_hedefkitle` = föy JSON'u;
     Logo satış satırı fiyatı (B2B/CRM siparişi, son ayın en yüksek birim fiyatı) CRM fiyatından farklıysa föyde
     «fiyat-logo» uyumsuzluğu var, değilse yok.
  5. CRM kampanyaları: `new_kampanyaBase` etkin, ayla kesişen = takvimdeki B2B kampanya kalemi sayısı.
  6. Çakışma: CRM'den aynı ISO hafta + aynı kitaplık ≥ 2 yeni kitap grupları = ekranda «ayni-hafta-kitaplik» işaretli
     kalemler.
  7. Paket: `foy/paket/{ay}.pdf` sayfa sayısı = onaylı föy sayısı; zip'teki PDF sayısı aynı.
  8. Teknoloji adı: ay ekranı, föy listesi ve paket PDF metninde 0.
  9. (bilgi) CRM bölge satış hedefi: kalemdeki adet = `new_satishedefleriBase` o ay kolonu toplamı; M46 ile ilişkisi
     ölçülecek, başarısızlık saymaz.
 10. (--write) Ay planı yoksa taslak kurulur: Σ `semantic_mkt_plan_lines.tutar` = plan toplamı = Σ bütçe satırı; gönderen
     onaylayamaz (403/409); plan geri çekilir. Satırlar cleanup.py ile silinir.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge.marketing import guard as G  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

BRIDGE = os.environ.get("M18_BRIDGE", "http://127.0.0.1:8795")
STATE = Path(os.environ.get("M18_STATE", "m18-kabul-state.json"))
SCHEMA = os.environ.get("CRM_SCHEMA", "Timas_MSCRM.dbo")


def api(method: str, path: str, body: Any = None, raw: bool = False) -> tuple[int, Any]:
    headers = {"Cookie": os.environ["M18_COOKIE"], "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")}
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


def near(a: Any, b: Any, tol: float = 0.01) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= tol


def utc(d: date) -> str:
    return f"DATEADD(HOUR, -3, '{d.isoformat()} 00:00:00')"


def pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page(?!s)", pdf))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ay", required=True, help="YYYY-AA")
    ap.add_argument("--write", action="store_true", help="plan yoksa taslak kur, bütçe toplamı ve onay kuralını dene")
    ap.add_argument("--allow-mail", action="store_true", help="bildirim alıcısı tanımlıyken de yazma denetimini koş")
    args = ap.parse_args()
    y, m = int(args.ay[:4]), int(args.ay[5:7])
    first = date(y, m, 1)
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    prev_last = first - timedelta(days=1)
    s = SemanticSettings.from_env()
    crm = bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = bsrc.runner(s.connection_file)
    firms = bsrc.firms_by_year(logo)
    store = open_store(s.store_dsn, create=False)
    out: dict[str, Any] = {"ay": args.ay, "checks": []}
    state: dict[str, Any] = json.loads(STATE.read_text()) if STATE.exists() else {"plans": [], "foy": [], "sends": []}
    # Paket indirmesinin değişiklik kaydı (nesne = ay) da kabul verisidir: başlangıç anı ve ay cleanup.py'ye bırakılır.
    from datetime import datetime, timezone

    state.setdefault("since", datetime.now(timezone.utc).isoformat())
    state["ay"] = args.ay
    state["actor"] = os.environ.get("M18_ACTOR", "timasai")
    STATE.write_text(json.dumps(state))

    def check(name: str, ok: bool, **detail: Any) -> None:
        out["checks"].append({"ad": name, "ok": bool(ok), **detail})

    def save() -> None:
        STATE.write_text(json.dumps(state))

    with store.engine.connect() as c:
        try:
            before_foy = {r[0] for r in c.execute(sa.text("SELECT id FROM semantic_mkt_foy WHERE donem = :d"), {"d": args.ay})}
            before_plan = {r[0] for r in c.execute(sa.text("SELECT id FROM semantic_mkt_plans WHERE kind = 'aylik' AND donem = :d"),
                                                   {"d": args.ay})}
        except Exception:  # noqa: BLE001 — tablo ilk kullanımda kurulur
            before_foy, before_plan = set(), set()

    # 10 --------------------------------------------------------------- (isteğe bağlı) taslağı kur
    if args.write:
        from semantic_bridge import admin as admin_mod

        admin_mod.ensure(store.engine)
        if (admin_mod.conf("MARKETING_ALERT_RECIPIENTS") or "").strip() and not args.allow_mail:
            check("10-yazma", False, hata="MARKETING_ALERT_RECIPIENTS dolu: onaya gönderme gerçek e-posta atar. --allow-mail ile koşun.")
            args.write = False
    if args.write and not before_plan:
        st, v = api("POST", f"/api/v1/marketing/months/{args.ay}/build")
        if st == 200 and v.get("plan"):
            state["plans"].append(v["plan"]["id"])
            save()
    st, view = api("GET", f"/api/v1/marketing/months/{args.ay}")
    if st != 200:
        check("ay-ekrani", False, hata=view)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 1
    st, foys = api("GET", f"/api/v1/marketing/foy?donem={args.ay}&yenile=1")
    with store.engine.connect() as c:
        after = {r[0] for r in c.execute(sa.text("SELECT id FROM semantic_mkt_foy WHERE donem = :d"), {"d": args.ay})}
    state["foy"] = sorted(set(state.get("foy", [])) | (after - before_foy))
    save()
    items = view.get("items") or []

    # 1 ---------------------------------------------------------------- ayın yeni kitapları
    ref = crm(f"""
SELECT k.new_StokKodu AS stok, k.new_kitaplikidName AS kitaplik, CAST(DATEADD(HOUR, 3, k.new_ilkyayintarihi) AS DATE) AS gun
FROM {SCHEMA}.new_kitap k
WHERE k.statecode = 0 AND k.new_Tip = 1 AND k.new_StokKodu IS NOT NULL
  AND k.new_ilkyayintarihi >= {utc(first)} AND k.new_ilkyayintarihi < {utc(nxt)}""")
    want = {str(r["stok"]).strip() for r in ref}
    screen = {x["stokKodu"] for x in items if x["tur"] == "yeni" and x["kaynak"] == "crm-kitap"
              and (x["detay"] or {}).get("yayinKaynagi") == "crm-kitap"}
    foy_codes = {f["stokKodu"] for f in (foys.get("items") if isinstance(foys, dict) else []) or [] if not f["ayDisi"]}
    check("1-ayin-yeni-kitaplari", view.get("plan") is None or want == screen, crm=len(want), takvim=len(screen),
          eksik=sorted(want - screen)[:50], fazla=sorted(screen - want)[:50], planYok=view.get("plan") is None)
    check("1b-foy-listesi", want <= foy_codes, crm=len(want), foy=len(foy_codes), eksik=sorted(want - foy_codes)[:50])

    # 2 ---------------------------------------------------------------- aylık hedef payı (M46)
    seg_ok, seg_detail = True, {}
    for seg in ("yeni", "backlist"):
        st, t = api("GET", f"/api/v1/budget/targets?year={y}&segment={seg}")
        if st != 200:
            seg_ok, seg_detail[seg] = False, str(t)[:200]
            continue
        total = round(sum(it["aylik"][m - 1]["ciro"] for it in t.get("items") or []), 2)
        shown = ((view["hedef"].get("segment") or {}).get(seg) or {}).get("ciro")
        ok = near(total, shown) if t.get("plan") else shown in (None, 0, 0.0)
        seg_ok &= ok
        seg_detail[seg] = {"butce": total, "ekran": shown}
    check("2-aylik-hedef-payi", seg_ok, **seg_detail)

    # 3 ---------------------------------------------------------------- önceki ay gerçekleşen (Logo STLINE)
    py, pm = prev_last.year, prev_last.month
    if py in firms:
        f = firms[py]
        r = logo(f"""
SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro
FROM dbo.LG_{f}_01_STLINE AS S JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{py}-{pm:02d}-01' AND S.DATE_ < '{first.isoformat()}' AND I.CODE NOT LIKE '157%'""")
        ref_ciro = float(r[0]["ciro"] or 0) if r else 0.0
        end = logo(bsrc.data_end_sql(firms[max(firms)]))
        ref_end = str(end[0]["son"])[:10] if end and end[0]["son"] else None
        o = view["oncekiAy"]
        check("3-onceki-ay-gerceklesen", near(ref_ciro, o.get("sirketCiro")) or (o.get("sirketCiro") is None and ref_ciro == 0),
              logo=round(ref_ciro, 2), ekran=o.get("sirketCiro"), veriSonuLogo=ref_end, veriSonuEkran=o.get("veriSonu"),
              not_=o.get("not"))
    else:
        check("3-onceki-ay-gerceklesen", False, hata=f"Logo'da {py} dönemi yok")

    # 4 ---------------------------------------------------------------- föy alanları ve Logo fiyatı
    sample = sorted(foy_codes)[:5]
    field_ok, detail = True, []
    for code in sample:
        q = code.replace("'", "''")
        rows = crm(f"""
SELECT k.new_ean13 AS ean, k.new_kdvdahilfiyat AS fiyat, k.new_TantmFyMetni AS tanitim, k.new_kitapspotu AS spot,
       k.new_hedefkitle AS hk FROM {SCHEMA}.new_kitapBase k WHERE k.statecode = 0 AND k.new_StokKodu = N'{q}'""")
        st, f = api("GET", f"/api/v1/marketing/foy/{code}?donem={args.ay}")
        if st != 200 or not rows:
            field_ok = False
            detail.append({"stok": code, "hata": str(f)[:200]})
            continue
        r = rows[0]
        fv = {a["key"]: a for a in f["alanlar"]}
        ean = re.sub(r"\D", "", str(r["ean"] or ""))
        ok_b = not ean or re.sub(r"\D", "", str(fv["barkod"]["deger"] or "")) == ean or fv["barkod"]["kaynak"] == "elle"
        ok_p = r["fiyat"] in (None, 0) or fv["fiyat"]["kaynak"] != "crm:new_kdvdahilfiyat" or near(r["fiyat"], fv["fiyat"]["deger"])
        norm = lambda v: " ".join(re.sub(r"<[^>]+>", " ", str(v or "")).split())  # noqa: E731
        ok_t = fv["tanitim"]["kaynak"] != "crm:new_TantmFyMetni" or norm(r["tanitim"]) == norm(fv["tanitim"]["deger"])
        lp = logo(f"""
SELECT TOP 1 MAX(CASE WHEN s.[Net Tutar] > 0 THEN s.[Birim Fiyat] END) AS fiyat, s.[Yıl] AS y, s.[Ay] AS a
FROM dbo.V_SatisRaporu_{date.today().year} s
WHERE s.[Malzeme/Hizmet Kodu] = N'{q}' AND s.[Satır Türü] = N'Malzeme' AND s.[Satis_Iade] = N'Satış'
  AND s.[Satıcı Kodu] NOT IN (N'CYERLIKAYA') AND LEFT(s.[Sipariş Numarası], 3) IN (N'B2B', N'CRM')
GROUP BY s.[Yıl], s.[Ay] HAVING MAX(CASE WHEN s.[Net Tutar] > 0 THEN 1 END) = 1 ORDER BY s.[Yıl] DESC, s.[Ay] DESC""")
        logo_price = float(lp[0]["fiyat"]) if lp and lp[0]["fiyat"] is not None else None
        flagged = any(x["tur"] == "fiyat-logo" for x in f["uyumsuzluk"])
        expect = logo_price is not None and r["fiyat"] not in (None, 0) and abs(logo_price - float(r["fiyat"])) > 0.01
        ok_m = flagged == expect or f["durum"] != "taslak"   # onaylı föyün uyumsuzluğu onay anındaki hâlidir
        field_ok &= ok_b and ok_p and ok_t and ok_m
        detail.append({"stok": code, "barkod": ok_b, "fiyat": ok_p, "tanitim": ok_t, "logoFiyat": logo_price,
                       "crmFiyat": r["fiyat"], "uyumsuzlukBekleniyor": expect, "uyumsuzlukVar": flagged})
    check("4-foy-alanlari", field_ok and bool(sample), ornek=detail,
          not_="Logo fiyatı yalnız bu yılın görünümünden: yeni kitapta satış satırı yoksa fiyat yok, uyumsuzluk beklenmez.")

    # 5 ---------------------------------------------------------------- CRM kampanyaları
    camps = crm(f"""
SELECT COUNT(*) AS n FROM {SCHEMA}.new_kampanyaBase c
WHERE c.statecode = 0 AND c.new_baslangictarihi < {utc(nxt)} AND c.new_bitistarihi >= {utc(first)}""")
    n_screen = sum(1 for x in items if x["tur"] == "b2b-kampanya" and x["kaynak"] == "crm-kampanya")
    check("5-crm-kampanyalari", view.get("plan") is None or int(camps[0]["n"]) == n_screen, crm=int(camps[0]["n"]), takvim=n_screen,
          not_="Yönetim'de kampanya tipi süzgeci doluysa fark beklenir.")

    # 6 ---------------------------------------------------------------- çakışma (aynı hafta + aynı kitaplık)
    groups: dict[tuple[str, str], set[str]] = {}
    for r in ref:
        if r["kitaplik"] and r["gun"]:
            d = date.fromisoformat(str(r["gun"])[:10])
            iy, iw, _ = d.isocalendar()
            groups.setdefault((f"{iy}-W{iw:02d}", str(r["kitaplik"]).strip().lower()), set()).add(str(r["stok"]).strip())
    want_c = {c for g in groups.values() if len(g) >= 2 for c in g}
    got_c = {x["stokKodu"] for x in items if any(k["kural"] == "ayni-hafta-kitaplik" for k in x.get("cakisma") or [])
             and x["kaynak"] == "crm-kitap" and not x["elle"]}
    check("6-cakisma", view.get("plan") is None or want_c == got_c, crm=sorted(want_c)[:50], ekran=sorted(got_c)[:50],
          not_="Elle kaydırılan kalem ve yayın günü proje/üretim kartından gelen kitap referansta farklı olabilir; fark listelenir.")

    # 7 ---------------------------------------------------------------- paket
    onayli = sum(1 for f in (foys.get("items") if isinstance(foys, dict) else []) or [] if f["durum"] == "onayli" and not f["ayDisi"])
    st1, pdf = api("GET", f"/api/v1/marketing/foy/paket/{args.ay}.pdf", raw=True)
    st2, zb = api("GET", f"/api/v1/marketing/foy/paket/{args.ay}.zip", raw=True)
    npdf = sum(1 for n in zipfile.ZipFile(io.BytesIO(zb)).namelist() if n.endswith(".pdf")) if st2 == 200 else None
    check("7-paket", st1 == 200 and st2 == 200 and (pages(pdf) == onayli or (onayli == 0 and pages(pdf) == 1)) and npdf == onayli,
          onayli=onayli, pdfSayfa=pages(pdf) if st1 == 200 else None, zipPdf=npdf)

    # 8 ---------------------------------------------------------------- teknoloji adı
    text = json.dumps(view, ensure_ascii=False) + json.dumps(foys, ensure_ascii=False) + (pdf.decode("latin-1", "ignore") if st1 == 200 else "")
    check("8-teknoloji-adi", not G.has_tech_name(text))

    # 9 ---------------------------------------------------------------- (bilgi) CRM bölge hedefi
    yv = {2023: 1, 2024: 2, 2025: 3, 2026: 100000000}.get(y)
    cols = ("new_ocak", "new_subat", "new_Mart", "new_Nisan", "new_mayis", "new_Haziran", "new_Temmuz", "new_agustos", "new_eylul",
            "new_Ekim", "new_kasim", "new_aralik")
    info = []
    for x in [x for x in items if x["tur"] == "yeni" and x["kaynak"] == "crm-kitap"][:10]:
        if yv is None:
            break
        q = x["stokKodu"].replace("'", "''")
        r = crm(f"SELECT SUM(COALESCE({cols[m - 1]}, 0)) AS adet FROM {SCHEMA}.new_satishedefleriBase "
                f"WHERE statecode = 0 AND new_yil = {yv} AND new_StokKodu = N'{q}'")
        info.append({"stok": x["stokKodu"], "crm": float(r[0]["adet"] or 0) if r else None,
                     "ekran": ((x["detay"] or {}).get("crmBolgeHedefi") or {}).get("adet")})
    out["bilgi-crm-bolge-hedefi"] = info

    # 10 --------------------------------------------------------------- yazma: bütçe toplamı ve iki göz
    if args.write and view.get("plan") and view["plan"]["id"] in state["plans"]:
        pid = view["plan"]["id"]
        with store.engine.connect() as c:
            dbsum = c.execute(sa.text("SELECT COALESCE(SUM(tutar), 0) FROM semantic_mkt_plan_lines WHERE plan_id = :p"), {"p": pid}).scalar()
        bsum = sum((b.get("tutar") or 0) for b in view.get("budget") or [])
        check("10a-butce-toplami", near(dbsum, view["plan"]["butceToplam"]) and near(dbsum, bsum), db=dbsum,
              plan=view["plan"]["butceToplam"], satir=bsum)
        st, _ = api("POST", f"/api/v1/marketing/months/{args.ay}/submit")
        if st == 200:
            st2, msg = api("POST", f"/api/v1/marketing/months/{args.ay}/approve", {})
            check("10b-gonderen-onaylayamaz", st2 in (403, 409), durum=st2, mesaj=str(msg)[:200])
            api("POST", f"/api/v1/marketing/months/{args.ay}/withdraw")
        else:
            check("10b-onaya-gonder", False, durum=st, not_="Bütçe satırı yoksa gönderilemez (kanal payı için CRM harcaması yok).")

    out["ozet"] = {"gecti": sum(1 for c in out["checks"] if c["ok"]), "kaldi": sum(1 for c in out["checks"] if not c["ok"])}
    out["elle"] = ["Föy ekranı 360 px genişlikte yatay kaydırmasız (tarayıcı, telefon düzeni)", "Paylaş düğmesi telefonda PDF paylaşır"]
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["ozet"]["kaldi"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
