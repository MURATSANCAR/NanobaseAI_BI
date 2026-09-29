#!/usr/bin/env python3
"""M36 Dijital yayın ve e-kitap — test sunucusunda gerçek CRM (.28) + Logo ile kabul ve ölçüm.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla; önce gece işi bir kez elle koşturulmuş olmalı —
`systemctl start timas-dijital.service` ya da
`curl -X POST -H "X-Semantic-Caller: $SEMANTIC_CALLER_TOKEN" http://127.0.0.1:8795/api/v1/dijital/run-due`,
süresi günlüğe yazılır):

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M36/kabul.py --olcum --out /tmp/claude-<oturum>/m36-kabul.json
    # Rapor yükleme (K6): yüklenmiş ve onaylanmış bir raporun dosyasıyla; net kolonunun başlığı verilir
    ... kabul.py --dosya /tmp/claude-<oturum>/rapor.xlsx --import DR-2026-0001 --net-kolon "Net Tutar"
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai)
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M36/kabul.py --api

Her kontrol: OK / FARK / DOĞRULANAMADI / ÖLÇÜM. Portalın tablosundaki (ekrana giden) değer, aynı CRM/Logo'da bağımsız
SQL ile karşılaştırılır; uygulamanın SQL'i yeniden koşturulmaz. Test verisi yazılmaz (yazma akışı ayrı: temizlik.py).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import dijital as D  # noqa: E402
from semantic_layer.profiler.connectors import connector_from_file  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []
ACTIVE = (100000000, 100000006, 100000007)


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:600]}")


def runner(path: str):
    conn = connector_from_file(path)
    conn.query_timeout = 1800

    def run(sql: str) -> list[dict]:
        _cols, rows, truncated = conn.execute(sql, 5_000_000)
        if truncated:
            raise RuntimeError("sonuç kesildi")
        return rows
    return run


def day(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def firms(logo) -> dict[int, str]:
    skip = {int(x) for x in os.environ.get("SEMANTIC_EXCLUDE_CONTEXT", "015,016").split(",") if x.strip().isdigit()}
    own = {int(x) for x in os.environ.get("SEMANTIC_FIRMS", "").split(",") if x.strip().isdigit()}   # canlı Logo başka şirketleri de taşır
    out: dict[int, int] = {}
    for r in logo("SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1"):
        f = int(r["FIRMNR"])
        if f in skip or (own and f not in own) or not day(r["BEGDATE"]) or not day(r["ENDDATE"]):
            continue
        for y in range(day(r["BEGDATE"]).year, day(r["ENDDATE"]).year + 1):
            out[y] = max(out.get(y, 0), f)
    return {y: f"{f:03d}" for y, f in out.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m36-kabul.json")
    ap.add_argument("--olcum", action="store_true")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--dosya")
    ap.add_argument("--import", dest="import_id")
    ap.add_argument("--net-kolon", dest="net_col")
    args = ap.parse_args()

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    D.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    st = D.settings_from(admin_mod.conf)
    p = st["schema"].rstrip(".") + "."
    crm = runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    ov = D.overview(engine, tenant, st)
    counts = D.meta_get(engine, tenant, "crm_counts")
    info = ov.get("okuma") or {}
    record("okuma yapıldı mı", "OK" if info.get("ok") else "DOĞRULANAMADI", son=info.get("_at"), sure_sn=info.get("sure"),
           kitap=info.get("kitap"), notlar=info.get("notlar"))
    if not info.get("ok"):
        return finish(args)

    # K1 Tip sayıları
    tips = {int(r["t"]): int(r["n"]) for r in crm(f"SELECT new_Tip AS t, COUNT(*) AS n FROM {p}new_kitapBase "
                                                   f"WHERE statecode = 0 AND new_Tip IN (8, 9) GROUP BY new_Tip")}
    ok = ov["kpi"]["ekitapKaydi"] == tips.get(8, 0) and ov["kpi"]["sesliKaydi"] == sum(tips.get(t, 0) for t in st["audioTypes"])
    record("K1 e-kitap / sesli kitap kaydı (Tip 8/9)", "OK" if ok else "FARK", portal=[ov["kpi"]["ekitapKaydi"], ov["kpi"]["sesliKaydi"]],
           referans=tips)

    # K2 Sözleşme düzeyi haklar
    ref = crm(f"SELECT COUNT(*) AS yururlukte, SUM(CASE WHEN new_EKitap = 1 THEN 1 ELSE 0 END) AS ekitap,"
              f" SUM(CASE WHEN new_SesliKitapHakki = 1 THEN 1 ELSE 0 END) AS sesli,"
              f" SUM(CASE WHEN new_iletimhakki = 1 THEN 1 ELSE 0 END) AS iletim FROM {p}new_sozlesmeBase"
              f" WHERE new_SozlesmeTipi = 5 AND statuscode IN (100000000, 100000006, 100000007)")[0]
    diff = {k: (counts.get(k), int(ref[k] or 0)) for k in ("yururlukte", "ekitap", "sesli", "iletim") if int(counts.get(k) or 0) != int(ref[k] or 0)}
    record("K2 sözleşme düzeyi e-kitap/sesli/iletim hakkı", "FARK" if diff else "OK", portal={k: counts.get(k) for k in ref},
           referans=ref, fark=diff, not_="2026-09-26 ölçümü: e-kitap 6.629, iletim 6.783")

    # K3 EPUB Evet
    n = int(crm(f"SELECT COUNT(*) AS n FROM {p}new_kitapBase WHERE statecode = 0 AND new_EPubDurumu = 1")[0]["n"])
    record("K3 CRM'de E-Pub: Evet", "OK" if ov["kpi"]["epubCrmEvet"] == n else "FARK", portal=ov["kpi"]["epubCrmEvet"], referans=n)

    # K4 Fırsat listesi: bağımsız hak kuralı + doğrudan Logo 12 ay
    k4(engine, tenant, st, crm, logo, p)

    # K5 Logo'da e-kitap satışı
    k5(engine, tenant, crm, logo, p)

    # K6 Rapor yükleme
    if args.dosya and args.import_id:
        k6(engine, args.dosya, args.import_id, args.net_col)
    else:
        with engine.connect() as c:
            imps = c.execute(sa.select(D.IMPORTS).where(D.IMPORTS.c.tenant_id == tenant)).all()
        for imp in imps:
            with engine.connect() as c:
                rows = c.execute(sa.select(sa.func.count(), sa.func.sum(D.SALES.c.net)).where(D.SALES.c.import_id == imp.id)).first()
            record(f"K6 rapor {imp.id} satır sayısı", "OK" if int(rows[0] or 0) == imp.satir else "FARK", tablo=int(rows[0] or 0),
                   kayit=imp.satir, not_="dosyayla karşılaştırma için --dosya/--import/--net-kolon")
        if not imps:
            record("K6 rapor yükleme", "DOĞRULANAMADI", neden="yüklenmiş rapor yok; Timaş'tan örnek platform raporu gelince")

    # K7 Hak notu
    n = int(crm(f"SELECT COUNT(*) AS n FROM {p}new_sozlesmeBase WHERE new_SozlesmeTipi = 5 AND ISNULL(new_haklaraciklama, '') <> ''")[0]["n"])
    record("K7 hak notu olan Telif Alış sözleşmesi", "OK" if int(counts.get("notlu") or 0) == n else "FARK", portal=counts.get("notlu"),
           referans=n, not_="2026-09-26 ölçümü: 738")

    # K8 İletim kararı (SEO/GEO) ile e-kitap kararı çelişkisi — ölçüm
    k8(engine, tenant)

    if args.olcum:
        olcum(crm, p)
    if args.api:
        api(engine, tenant, st)
    return finish(args)


def book_rights(crm, p: str, flag_col: str) -> dict[str, str]:
    """Bağımsız hak kuralı (kitap → var/eksik/incele/yok/koruma_disi) doğrudan SQL satırlarından."""
    rows = crm(f"SELECT sk.new_kitapid AS k, s.statuscode AS st, s.new_SozlesmeBitisTarihi AS bitis,"
               f" CAST(ISNULL(s.new_suresizsozlesme, 0) AS int) AS suresiz, s.new_fesihtarihi AS fesih,"
               f" CAST(ISNULL(s.{flag_col}, 0) AS int) AS hak, CAST(ISNULL(s.new_KorumaDEser, 0) AS int) AS kd,"
               f" CASE WHEN ISNULL(s.new_haklaraciklama, '') <> '' THEN 1 ELSE 0 END AS notlu"
               f" FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid"
               f" WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5")
    today = date.today()
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(str(r["k"]).upper(), []).append(r)
    out = {}
    for k, cs in by.items():
        live = []
        for c in cs:
            if int(c["st"] or 0) not in ACTIVE:
                continue
            cut, end = day(c["fesih"]), day(c["bitis"])
            if cut and cut <= today:
                continue
            if c["suresiz"] or end is None or end >= today:
                live.append(c)
        if not live:
            out[k] = "koruma_disi" if any(c["kd"] for c in cs) else "yok"
        elif any(not c["hak"] for c in live):
            out[k] = "eksik"
        elif any(c["notlu"] for c in live):
            out[k] = "incele"
        else:
            out[k] = "var"
    return out


def window(end: date) -> tuple[int, int]:
    last = end.year * 12 + end.month
    return last - 11, last


def k4(engine, tenant, st, crm, logo, p) -> None:
    info = D.meta_get(engine, tenant, "logo")
    if not info.get("veriSonu"):
        record("K4 fırsat listesi", "DOĞRULANAMADI", neden="Logo okuması yok")
        return
    end = date.fromisoformat(info["veriSonu"])
    lo, hi = window(end)
    fm = firms(logo)
    qty: dict[str, float] = {}
    for y in range((lo - 1) // 12, end.year + 1):
        if y not in fm:
            continue
        for r in logo(f"SELECT I.CODE AS c, SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS a"
                      f" FROM dbo.LG_{fm[y]}_01_STLINE S JOIN dbo.LG_{fm[y]}_ITEMS I ON I.LOGICALREF = S.STOCKREF"
                      f" WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
                      f" AND YEAR(S.DATE_) = {y} AND YEAR(S.DATE_) * 12 + MONTH(S.DATE_) BETWEEN {lo} AND {hi} GROUP BY I.CODE"):
            k = re.sub(r"\s+", "", str(r["c"] or "").upper())
            qty[k] = qty.get(k, 0.0) + float(r["a"] or 0)
    rights = book_rights(crm, p, "new_EKitap")
    books = crm(f"SELECT new_kitapId AS id, new_StokKodu AS s, new_kitap_yayincilikstatusu AS ys FROM {p}new_kitapBase"
                f" WHERE statecode = 0 AND new_Tip = 1 AND ISNULL(new_EKitapStokKodu, '') = ''")
    labels = {int(r["v"]): str(r["l"]) for r in crm(
        f"SELECT sm.AttributeValue AS v, sm.Value AS l FROM {p}StringMap sm WHERE sm.LangId = 1055 AND sm.AttributeName = 'new_kitap_yayincilikstatusu'")}
    flagged = set(D.OUT_OF_SALE)
    with engine.connect() as c:
        live = {r[0] for r in c.execute(sa.select(D.TITLES.c.kitap_id).where(D.TITLES.c.tenant_id == tenant, D.TITLES.c.ekitap_var.is_(True))).all()}
        decided = {r[0] for r in c.execute(sa.select(D.DECISIONS.c.kitap_id).where(D.DECISIONS.c.tenant_id == tenant)).all()}
        portal = c.execute(sa.select(D.TITLES.c.kitap_id, D.TITLES.c.basili_12ay_adet).where(D.TITLES.c.tenant_id == tenant,
                                                                                             D.TITLES.c.firsat_puani.is_not(None))
                           .order_by(sa.desc(D.TITLES.c.basili_12ay_adet), D.TITLES.c.ad)).all()
    ref = []
    for b in books:
        kid = str(b["id"]).upper()
        code = re.sub(r"\s+", "", str(b["s"] or "").upper())
        ys = labels.get(int(b["ys"])) if b.get("ys") is not None else ""
        if (ys or "").split(" ", 1)[0].upper() in flagged or kid in live or kid in decided:
            continue
        if rights.get(kid) == "var" and qty.get(code, 0) >= st["oppMinQty"]:
            ref.append((kid, qty[code]))
    ref.sort(key=lambda x: -x[1])
    pset = {r[0] for r in portal if r[0] not in decided}
    rset = {k for k, _ in ref}
    ok = pset == rset
    record("K4 fırsat listesi (e-kitap)", "OK" if ok else "FARK", portal=len(pset), referans=len(rset),
           yalniz_portal=sorted(pset - rset)[:10], yalniz_referans=sorted(rset - pset)[:10], pencere=[lo, hi], esik=st["oppMinQty"],
           not_="hak kararı yazılmış (kismi dahil) ve platformda yayında kitaplar iki taraftan da düşüldü")
    top_p = [r[0] for r in portal if r[0] in rset][:20]
    top_r = [k for k, _ in ref][:20]
    record("K4 fırsat ilk 20 sıra", "OK" if top_p == top_r else "FARK", portal=top_p, referans=top_r)


def k5(engine, tenant, crm, logo, p) -> None:
    codes = [str(r["c"]).strip() for r in crm(f"SELECT DISTINCT new_EKitapStokKodu AS c FROM {p}new_kitapBase WHERE statecode = 0"
                                                f" AND ISNULL(new_EKitapStokKodu, '') <> ''")]
    info = D.meta_get(engine, tenant, "logo")
    if not codes:
        record("K5 Logo'da e-kitap satışı", "ÖLÇÜM", bulgu="CRM'de e-kitap stok kodu dolu kitap yok")
        return
    end = date.fromisoformat(info["veriSonu"]) if info.get("veriSonu") else None
    if not end:
        record("K5 Logo'da e-kitap satışı", "DOĞRULANAMADI", neden="Logo okuması yok")
        return
    lo, hi = window(end)
    fm = firms(logo)
    ref: dict[str, float] = {}
    values = ", ".join("(N'" + c.replace("'", "''") + "')" for c in codes)
    for y in range((lo - 1) // 12, end.year + 1):
        if y not in fm:
            continue
        for r in logo(f"SELECT it.CODE AS c, SUM(CASE WHEN s.TRCODE IN (7,8,9) THEN s.AMOUNT ELSE -s.AMOUNT END) AS a"
                      f" FROM dbo.LG_{fm[y]}_01_STLINE s JOIN dbo.LG_{fm[y]}_ITEMS it ON it.LOGICALREF = s.STOCKREF"
                      f" JOIN (VALUES {values}) v(kod) ON v.kod = it.CODE"
                      f" WHERE s.TRCODE IN (2,3,7,8,9) AND s.LINETYPE = 0 AND s.CANCELLED = 0 AND s.INVOICEREF <> 0"
                      f" AND YEAR(s.DATE_) = {y} AND YEAR(s.DATE_) * 12 + MONTH(s.DATE_) BETWEEN {lo} AND {hi} GROUP BY it.CODE"):
            ref[str(r["c"]).strip().upper()] = ref.get(str(r["c"]).strip().upper(), 0.0) + float(r["a"] or 0)
    portal = {k.upper(): sum(m["adet"] for m in v["aylar"].values()) for k, v in (info.get("ekitapSatis") or {}).items()}
    diff = {k: (portal.get(k), ref.get(k)) for k in set(portal) | set(ref) if abs((portal.get(k) or 0) - (ref.get(k) or 0)) > 0.001}
    if not ref:
        # Boş sonuç bulgudur; doğru olup olmadığı 2021–2025 kopyasında da sorulur.
        old = []
        if 2025 in fm:
            old = logo(f"SELECT TOP 5 it.CODE AS c FROM dbo.LG_{fm[2025]}_01_STLINE s JOIN dbo.LG_{fm[2025]}_ITEMS it"
                       f" ON it.LOGICALREF = s.STOCKREF JOIN (VALUES {values}) v(kod) ON v.kod = it.CODE WHERE s.CANCELLED = 0")
        record("K5 Logo'da e-kitap satışı", "ÖLÇÜM", bulgu="son 12 ayda e-kitap stok koduyla fatura yok", kod=len(codes),
               eski_donemde_hareket=[r["c"] for r in old], portal_bos=not portal)
        return
    record("K5 Logo'da e-kitap satışı", "FARK" if diff else "OK", kod=len(codes), satan=len(ref), fark=dict(list(diff.items())[:10]))


def k6(engine, path: str, iid: str, net_col: str | None) -> None:
    data = Path(path).read_bytes()
    rows = D.extract_rows(path, data)
    det = D.detect_columns(rows)
    header = [str(h or "").strip() for h in rows[det["header_row"]]]
    j = header.index(net_col) if net_col and net_col in header else det["mapping"].get("net")
    body = [r for r in rows[det["header_row"] + 1:] if any(c not in (None, "") and str(c).strip() for c in r)]
    ref_net = sum(D.parse_number(r[j]) or 0 for r in body if j is not None and j < len(r))
    with engine.connect() as c:
        n, net = c.execute(sa.select(sa.func.count(), sa.func.sum(D.SALES.c.net)).where(D.SALES.c.import_id == iid)).first()
        n_ok, net_ok = c.execute(sa.select(sa.func.count(), sa.func.sum(D.SALES.c.net))
                                 .where(D.SALES.c.import_id == iid, D.SALES.c.tur == "satir")).first()
    record("K6 rapor satır sayısı (hiçbir satır atılmaz)", "OK" if int(n or 0) == len(body) else "FARK", tablo=n, dosya=len(body))
    record("K6 rapor net toplamı (özet satırı dahil)", "OK" if abs(float(net or 0) - ref_net) < 0.01 else "FARK", tablo=net, dosya=ref_net,
           ozetsiz=net_ok, not_="özet (toplam) satırı ekranda toplama girmez; dosya toplamı tablo toplamıyla aynı olmalı")


def k8(engine, tenant) -> None:
    try:
        with engine.connect() as c:
            seo = {str(r[0]).upper(): r[1] for r in c.execute(sa.text("SELECT book_id, rights FROM semantic_seo_crm_books")).all()}
            ours = {r[0]: r[1] for r in c.execute(sa.select(D.TITLES.c.kitap_id, D.TITLES.c.hak_ekitap).where(D.TITLES.c.tenant_id == tenant)).all()}
    except Exception as e:  # noqa: BLE001
        record("K8 iletim kararı ↔ e-kitap kararı", "DOĞRULANAMADI", neden=str(e)[:200])
        return
    both = [k for k in ours if k in seo]
    clash = [k for k in both if ours[k] == "var" and seo[k] in ("eksik", "yok")]
    record("K8 iletim kararı ↔ e-kitap kararı", "ÖLÇÜM", ortak=len(both), ekitap_var_iletim_yok=len(clash), ornek=clash[:10])


def olcum(crm, p) -> None:
    for name, sql in (
        ("Ö1 sesli kitap hakkı (yürürlükte sözleşme)", f"SELECT COUNT(*) AS n FROM {p}new_sozlesmeBase WHERE new_SozlesmeTipi = 5"
                                                     f" AND statuscode IN (100000000, 100000006, 100000007) AND new_SesliKitapHakki = 1"),
        ("Ö2 dijital kimlik doluluğu (Tip 1)", f"SELECT COUNT(*) AS kitap, SUM(CASE WHEN ISNULL(new_ekitapisbn,'') <> '' THEN 1 ELSE 0 END) AS e_isbn,"
                                              f" SUM(CASE WHEN ISNULL(new_EKitapBarkod,'') <> '' THEN 1 ELSE 0 END) AS e_barkod,"
                                              f" SUM(CASE WHEN ISNULL(new_EKitapStokKodu,'') <> '' THEN 1 ELSE 0 END) AS e_stok"
                                              f" FROM {p}new_kitapBase WHERE statecode = 0 AND new_Tip = 1"),
        ("Ö3 e-kitap üretim aşaması", f"SELECT statuscode AS d, COUNT(*) AS n FROM {p}new_UretimBase WHERE statuscode IN (100000011, 100000012)"
                                     f" GROUP BY statuscode"),
        ("Ö4 kitap geçmişi (son 90 gün)", f"SELECT COUNT(*) AS n, COUNT(DISTINCT new_kitapid) AS kitap FROM {p}new_kitapgecmisiBase"
                                         f" WHERE CreatedOn >= DATEADD(day, -90, GETDATE())"),
    ):
        try:
            record(name, "ÖLÇÜM", sonuc=crm(sql))
        except Exception as e:  # noqa: BLE001
            record(name, "DOĞRULANAMADI", neden=str(e)[:200])


def api(engine, tenant, st) -> None:
    base, cookie = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795"), os.environ.get("TIMAS_COOKIE", "")
    if not cookie:
        record("API", "DOĞRULANAMADI", neden="TIMAS_COOKIE yok")
        return

    def get(path: str):
        req = urllib.request.Request(base + path, headers={"cookie": cookie,
                                                           "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())

    ov = get("/api/v1/dijital/overview")
    ref = D.overview(engine, tenant, st)
    record("API göstergeler = tablo", "OK" if ov["kpi"] == ref["kpi"] else "FARK", api=ov["kpi"], tablo=ref["kpi"])
    t = get("/api/v1/dijital/titles?durum=firsat")
    record("API fırsat süzgeci toplamı = gösterge", "OK" if t["total"] == ref["kpi"]["firsat"] else "FARK", api=t["total"], kpi=ref["kpi"]["firsat"])
    o = get("/api/v1/dijital/opportunities")
    record("API fırsat listesi toplamı", "OK" if o["total"] == ref["kpi"]["firsat"] else "FARK", api=o["total"])
    rr = get("/api/v1/dijital/rights-risks")
    record("API hak riski = gösterge", "OK" if len(rr["risk"]) == ref["kpi"]["hakRiski"] else "FARK", api=len(rr["risk"]), kpi=ref["kpi"]["hakRiski"])
    try:
        req = urllib.request.Request(base + "/api/v1/dijital/imports", method="POST", data=b"",
                                     headers={"cookie": cookie, "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
        urllib.request.urlopen(req, timeout=60)
        record("API boş yükleme reddi", "FARK", neden="boş gövde kabul edildi")
    except urllib.error.HTTPError as e:
        record("API boş yükleme reddi", "OK" if e.code in (400, 403, 404, 422) else "FARK", kod=e.code)


def finish(args) -> int:
    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
    bad = [r for r in RESULTS if r["durum"] == "FARK"]
    print(f"\n{len(RESULTS)} kontrol, {len(bad)} FARK → {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
