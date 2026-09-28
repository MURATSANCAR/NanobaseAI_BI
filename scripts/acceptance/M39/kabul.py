#!/usr/bin/env python3
"""M39 Pazar araştırması ve rekabet — test sunucusunda gerçek CRM (.28) + Logo ile kabul ve ölçüm.

Koşturma (köprünün sanal ortamında, köprünün env dosyasıyla; önce bir kez `run-due` elle koşturulmuş olmalı ve süresi
günlüğe yazılır — bellek: run-it-before-it-runs-itself):

    curl -fsS -X POST -H "X-Semantic-Caller: $SEMANTIC_CALLER_TOKEN" 'http://127.0.0.1:8795/api/v1/pazar/run-due?budget=600&brief=false'
    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M39/kabul.py --olcum --out /tmp/claude-<oturum>/m39-kabul.json
    # API da denenecekse: timasai'nin 15 dk'lık oturum çerezi (bellek: test-login-as-timasai), bitince oturum silinir
    BRIDGE_URL=http://127.0.0.1:8795 TIMAS_COOKIE='timas_session=…' python3 ../scripts/acceptance/M39/kabul.py --api

Bölümler (her kontrol: OK / FARK / DOĞRULANAMADI / ÖLÇÜM / ELLE):
- **K (kabul):** portalın kendi tablolarındaki değer (ekrana giden `pazar.*` işlevi) ↔ aynı CRM/Logo'da bağımsız SQL
  (`referans.sql`). K1 katalog ve tazelik, K2 yayınevi fiyat bandı (5 yayınevi), K3 TİMAŞ fiyat bandı (toplam + 3
  kategori), K4 emsal bağı, K5 yayınevi (marka) cirosu aynı dönem, K6 kanal cirosu ve payı, K7 onaylı rapor rakamı
  sayfada (10 örnek; sayfayı açıp bakmak ELLE), K8 onaylı özetin her maddesi kaynağa bağlı, K9 onaylı eşlemenin kayıt
  sayısı.
- **Ö (ölçüm, --olcum):** «Satış adedi» alanlarının doluluğu, alma partisi sayısı, ham kategori ayırıcıları, kayıtlı
  SQL'lerle (TOTAL / NETTOTAL) tanım farkı. Sonuç günlüğe ve analiz belgesine yazılır.
- **A (--api):** köprü uçlarının cevabı ↔ aynı referans; geçersiz gövdeli yazma denemeleri 400/422 (kayıt açmaz).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import pazar as P  # noqa: E402
from semantic_bridge import pazar_sources as src  # noqa: E402
from semantic_bridge.editorial import _prefix  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:600]}")


def close(a, b, tol=0.01) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol


def q(s: str) -> str:
    return str(s).replace("'", "''")


def d19(v) -> str:
    return (src.day(v) or "")[:19]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m39-kabul.json")
    ap.add_argument("--olcum", action="store_true")
    ap.add_argument("--api", action="store_true")
    ap.add_argument("--ornek", type=int, default=5)
    args = ap.parse_args()
    n = max(5, args.ornek)

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    P.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    crm = src.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))
    logo = src.runner(os.environ["SEMANTIC_CONNECTION_FILE"])
    p = _prefix(admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo")
    snap = P.meta_get(engine, tenant, "snapshot", {}) or {}
    record("anlık görüntü var mı", "OK" if snap.get("at") else "DOĞRULANAMADI", at=snap.get("at"),
           kategoriKaynagi=snap.get("categorySource"), hatalar=snap.get("errors"), logo=snap.get("ownSales"))
    if not snap.get("at"):
        return finish(args)

    # K1 — katalog ve tazelik
    ref = crm(f"SELECT COUNT(*) AS kayit, MIN(CreatedOn) AS ilk, MAX(CreatedOn) AS son, MAX(ModifiedOn) AS degisme "
              f"FROM {p}new_rakipkitapBase WHERE statecode = 0")[0]
    fr = P.freshness(engine, tenant)
    ok = (int(ref["kayit"]) == fr["records"] and d19(ref["ilk"]) == (fr["firstCreated"] or "")[:19]
          and d19(ref["son"]) == (fr["lastCreated"] or "")[:19] and d19(ref["degisme"]) == (fr["lastModified"] or "")[:19])
    record("K1 rakip katalog ve tazelik", "OK" if ok else "FARK",
           portal={k: fr[k] for k in ("records", "firstCreated", "lastCreated", "lastModified", "ageDays")},
           referans={k: (str(v) if v is not None else None) for k, v in ref.items()},
           not_="anlık görüntüden sonra CRM'e kayıt eklendiyse fark beklenir; run-due'dan hemen sonra koşturun")

    # K2 — yayınevi fiyat bandı (en çok kaydı olan n yayınevi)
    m = P.matrix(engine, tenant)
    top = [r for r in m["rows"] if r["fiyatli"]][:n]
    refs = crm(f"""SELECT DISTINCT new_Yaynevi AS yayinevi, COUNT(*) OVER (PARTITION BY new_Yaynevi) AS fiyatli,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY new_ListeFiyat) OVER (PARTITION BY new_Yaynevi) AS medyan,
  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY new_ListeFiyat) OVER (PARTITION BY new_Yaynevi) AS q1,
  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY new_ListeFiyat) OVER (PARTITION BY new_Yaynevi) AS q3
FROM {p}new_rakipkitapBase WHERE statecode = 0 AND new_ListeFiyat > 0""")
    by = {}
    for r in refs:
        by.setdefault(src.clean(r["yayinevi"]) or "(yayınevi yok)", []).append(r)
    for r in top:
        hits = by.get(r["yayinevi"], [])
        if len(hits) != 1:
            record(f"K2 fiyat bandı {r['yayinevi']}", "DOĞRULANAMADI", neden="ham yazımda birden çok karşılık (boşluk/HTML)", adet=len(hits))
            continue
        x = hits[0]
        ok = int(x["fiyatli"]) == r["fiyatli"] and all(close(r[k], x[k], 0.005) for k in ("medyan", "q1", "q3"))
        record(f"K2 fiyat bandı {r['yayinevi']}", "OK" if ok else "FARK",
               portal={k: r[k] for k in ("fiyatli", "medyan", "q1", "q3")}, referans={k: x[k] for k in ("fiyatli", "medyan", "q1", "q3")})

    # K3 — TİMAŞ fiyat bandı: toplam ve (kitaplık kaynağında) 3 kategori
    def own_ref(extra: str = "") -> dict:
        rows = crm(f"SELECT DISTINCT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY new_kdvdahilfiyat) OVER () AS medyan, "
                   f"COUNT(*) OVER () AS n FROM {p}new_kitapBase WHERE statecode = 0 AND new_Tip = 1 AND new_kdvdahilfiyat > 0{extra}")
        return rows[0] if rows else {"medyan": None, "n": 0}

    x = own_ref()
    t = m["timas"][0]
    record("K3 TİMAŞ medyan fiyat (tümü)", "OK" if int(x["n"]) == t["fiyatli"] and close(x["medyan"], t["medyan"], 0.005) else "FARK",
           portal={"fiyatli": t["fiyatli"], "medyan": t["medyan"]}, referans=x)
    if snap.get("categorySource") == "kitaplik":
        with engine.connect() as c:
            kats = c.execute(sa.select(P.OWN_BOOKS.c.kategori_id, sa.func.count().label("k")).where(
                P.OWN_BOOKS.c.tenant_id == tenant, P.OWN_BOOKS.c.kategori_id.isnot(None))
                .group_by(P.OWN_BOOKS.c.kategori_id).order_by(sa.desc("k")).limit(3)).all()
        for k in kats:
            mk = P.matrix(engine, tenant, kategori=k.kategori_id)["timas"][0]
            x = own_ref(f" AND new_kitaplikid = '{q(k.kategori_id)}'")
            record(f"K3 TİMAŞ medyan fiyat kitaplık {k.kategori_id}", "OK" if int(x["n"]) == mk["fiyatli"] and close(x["medyan"], mk["medyan"], 0.005)
                   else "FARK", portal={"fiyatli": mk["fiyatli"], "medyan": mk["medyan"]}, referans=x)
    else:
        record("K3 TİMAŞ medyan fiyat kategori kırılımı", "ÖLÇÜM", neden="kategori kaynağı ağaç; kitabın düğümü köprünün tablosunda "
               "(H1 profili), CRM'de karşılığı tek kolon değil — kategori başına referans H1 kabulündedir")

    # K4 — emsal bağı
    x = crm(f"SELECT COUNT(*) AS bag, COUNT(DISTINCT CONCAT(new_kitapid, '|', new_rakipkitapid)) AS tekil "
            f"FROM {p}new_new_kitap_new_rakipkitapBase")[0]
    record("K4 CRM'de kayıtlı emsal bağı", "OK" if int(x["tekil"]) == fr["crmLinks"] else "FARK", portal=fr["crmLinks"], referans=x)
    with engine.connect() as c:
        sample = c.execute(sa.select(P.LINKS.c.kitap_crm_id).where(P.LINKS.c.tenant_id == tenant).limit(1)).first()
    if sample:
        want = {src.guid(r["r"]) for r in crm(f"SELECT new_rakipkitapid AS r FROM {p}new_new_kitap_new_rakipkitapBase "
                                              f"WHERE new_kitapid = '{q(sample.kitap_crm_id)}'")}
        got = {x["id"] for x in P.comparables(engine, tenant, {"crmKitapId": sample.kitap_crm_id}, None)["rakip"] if x["crmEmsal"]}
        record(f"K4b bir kitabın emsalleri {sample.kitap_crm_id}", "OK" if want == got else "FARK", portal=sorted(got), referans=sorted(want),
               not_="aktif olmayan (statecode=1) rakip kayıt portalda yoktur; fark varsa bundandır")

    # K5, K6 — iç göstergeler (aynı dönem)
    firms = src.firms_by_year(logo)
    end = src.read_data_end(logo, firms)
    mm = P.own_market(engine, tenant, "yayinevi")
    if not end or not mm.get("yil"):
        record("K5/K6 iç göstergeler", "DOĞRULANAMADI", neden="Logo satışı okunmadı", snap=snap.get("errors"))
    else:
        y = mm["yil"]
        cut = src.cut_day(y, end)
        f = firms[y]
        rows = logo(f"""SELECT COALESCE(NULLIF(I.SPECODE, ''), '(boş)') AS k,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet
FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{y}-01-01' AND S.DATE_ < '{cut.isoformat()}'
GROUP BY COALESCE(NULLIF(I.SPECODE, ''), '(boş)')""")
        ref = {(src.clean(r["k"]) or "(boş)"): r for r in rows}
        for r in mm["rows"][:n]:
            x = ref.get(r["ad"])
            ok = x is not None and close(r["ytdCiro"], x["ciro"], 1.0) and close(r["ytdAdet"], x["adet"], 0.001)
            record(f"K5 yayınevi cirosu {r['ad']} {y}", "OK" if ok else "FARK", portal={"ciro": r["ytdCiro"], "adet": r["ytdAdet"]},
                   referans=x, donem=[f"{y}-01-01", cut.isoformat()])
        mk = P.own_market(engine, tenant, "kanal", y)
        rows = logo(f"""SELECT COALESCE(NULLIF(C.SPECODE2, ''), '(boş)') AS k,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro
FROM dbo.LG_{f}_01_STLINE S LEFT JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{y}-01-01' AND S.DATE_ < '{cut.isoformat()}'
GROUP BY COALESCE(NULLIF(C.SPECODE2, ''), '(boş)')""")
        ref = {(src.clean(r["k"]) or "(boş)"): float(r["ciro"] or 0) for r in rows}
        total = sum(ref.values())
        for r in mk["rows"][:n]:
            x = ref.get(r["ad"])
            ok = x is not None and close(r["ytdCiro"], x, 1.0) and close(r["pay"], (x / total) if total else None, 1e-6)
            record(f"K6 kanal cirosu ve payı {r['ad']} {y}", "OK" if ok else "FARK", portal={"ciro": r["ytdCiro"], "pay": r["pay"]},
                   referans={"ciro": x, "pay": (x / total) if (x is not None and total) else None})
        if args.olcum:
            olcum_defs(logo, f, y, cut, mm, mk)

    # K7 — onaylı rapor rakamları sayfada
    figs = P.approved_figures(engine, tenant)[:10]
    if not figs:
        record("K7 onaylı rapor rakamı", "DOĞRULANAMADI", neden="onaylı rakam yok (rapor yüklenip rakam onaylanınca koşturun)")
    pages_cache: dict[str, dict[str, str]] = {}
    for fg in figs:
        path, name, _ = P.report_file(engine, tenant, fg["raporId"])
        if fg["raporId"] not in pages_cache:
            pages_cache[fg["raporId"]] = {pg["sayfa"]: pg["metin"] for pg in src.pages_of(name, Path(path).read_bytes())}
        text = pages_cache[fg["raporId"]].get(fg["sayfa"], "")
        found = P.value_in_text(fg["degerMetin"] or P.fmt_tr(fg["deger"], 2), text) is not None
        status = "OK" if found else ("ELLE" if fg["yontem"] == "elle" or fg["durum"] == "duzeltildi" else "FARK")
        record(f"K7 rakam s.{fg['sayfa']} «{fg['gosterge'][:60]}»", status, deger=fg["deger"], birim=fg["birim"], rapor=fg["rapor"],
               dosya=path, not_="sayfayı açıp değeri elle doğrulayın; doğruluk oranı günlüğe yazılır")

    # K8 — onaylı özetin her maddesi kaynağa bağlı
    with engine.connect() as c:
        briefs = c.execute(sa.select(P.BRIEFS).where(P.BRIEFS.c.tenant_id == tenant, P.BRIEFS.c.durum == "onaylandi")).all()
    if not briefs:
        record("K8 onaylı özet", "DOĞRULANAMADI", neden="onaylı özet yok")
    for b in briefs:
        problems = P.check_brief(b.taslak_md, (P.loads(b.kaynaklar_json, {}) or {}).get("kaynaklar", []))
        record(f"K8 özet {b.donem} maddeleri kaynaklı", "OK" if not problems else "FARK", sorunlar=problems[:5])

    # K9 — onaylı eşlemenin kayıt sayısı
    with engine.connect() as c:
        maps = c.execute(sa.select(P.CATEGORY_MAP).where(P.CATEGORY_MAP.c.tenant_id == tenant, P.CATEGORY_MAP.c.durum == "onaylandi")
                         .order_by(P.CATEGORY_MAP.c.kayit_sayisi.desc()).limit(n)).all()
    if not maps:
        record("K9 onaylı eşleme", "DOĞRULANAMADI", neden="onaylı eşleme yok")
    for mp in maps:
        refs = crm(f"SELECT new_Kategoriler AS k, COUNT(*) AS kayit FROM {p}new_rakipkitapBase WHERE statecode = 0 "
                   f"AND new_Kategoriler LIKE N'%{q(mp.kategori_ham[:60])}%' GROUP BY new_Kategoriler")
        want = sum(int(r["kayit"]) for r in refs if src.norm_category(r["k"]) == mp.kategori_ham)
        with engine.connect() as c:
            got = c.execute(sa.select(sa.func.count()).select_from(P.COMPETITORS).where(
                P.COMPETITORS.c.tenant_id == tenant, P.COMPETITORS.c.kategori_ham == mp.kategori_ham,
                P.COMPETITORS.c.kategori_id == mp.kategori_id)).scalar()
        record(f"K9 eşleme «{mp.kategori_ham[:50]}»", "OK" if want == got else "FARK", portal=got, referans=want)

    if args.olcum:
        olcum_crm(crm, p)
    if args.api:
        api_checks(fr, m)
    return finish(args)


def olcum_crm(crm, p: str) -> None:
    x = crm(f"""SELECT COUNT(*) AS kayit, SUM(CASE WHEN new_SatisAdedi IS NOT NULL THEN 1 ELSE 0 END) AS satis1_dolu,
  SUM(CASE WHEN NULLIF(new_SatAdedi2, '') IS NOT NULL THEN 1 ELSE 0 END) AS satis2_dolu,
  COUNT(DISTINCT ImportSequenceNumber) AS alma_partisi, COUNT(DISTINCT new_Kategoriler) AS ham_kategori,
  SUM(CASE WHEN new_Kategoriler LIKE '%>%' THEN 1 ELSE 0 END) AS buyuktur_ayirici,
  SUM(CASE WHEN new_Kategoriler LIKE '%,%' THEN 1 ELSE 0 END) AS virgul_ayirici,
  SUM(CASE WHEN new_ListeFiyat > 0 THEN 1 ELSE 0 END) AS fiyatli, SUM(CASE WHEN new_SayfaSays > 0 THEN 1 ELSE 0 END) AS sayfali
FROM {p}new_rakipkitapBase WHERE statecode = 0""")[0]
    record("Ö1 rakip alan doluluğu ve alma partileri", "ÖLÇÜM", **{k: v for k, v in x.items()})
    rows = crm(f"SELECT TOP 20 new_Kategoriler AS k, COUNT(*) AS kayit FROM {p}new_rakipkitapBase WHERE statecode = 0 "
               f"GROUP BY new_Kategoriler ORDER BY COUNT(*) DESC")
    record("Ö2 en sık ham kategoriler", "ÖLÇÜM", ilk20=[[r["k"], r["kayit"]] for r in rows])


def olcum_defs(logo, f: str, y: int, cut: date, mm: dict, mk: dict) -> None:
    """Kayıtlı SQL'lerin tanımıyla (TOTAL / fatura başlığı NETTOTAL, faturasız dahil) portalın tanımı (LINENET, faturalı)
    arasındaki fark: aynı dönemde toplam."""
    a = logo(f"""SELECT SUM(CASE WHEN S.TRCODE IN (7,8) THEN S.TOTAL ELSE -S.TOTAL END) AS v
FROM dbo.LG_{f}_01_STLINE S WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.TRCODE IN (2,3,7,8)
  AND S.DATE_ >= '{y}-01-01' AND S.DATE_ < '{cut.isoformat()}'""")[0]["v"]
    b = logo(f"""SELECT SUM(CASE WHEN I.TRCODE IN (7,8,9) THEN I.NETTOTAL ELSE -I.NETTOTAL END) AS v
FROM dbo.LG_{f}_01_INVOICE I WHERE I.CANCELLED = 0 AND I.TRCODE IN (2,3,7,8,9)
  AND I.DATE_ >= '{y}-01-01' AND I.DATE_ < '{cut.isoformat()}'""")[0]["v"]
    record("Ö3 tanım farkı (yayınevi SQL'i, TOTAL)", "ÖLÇÜM", portal_LINENET=(mm.get("total") or {}).get("ytdCiro"), kayitli_sql_TOTAL=a)
    record("Ö4 tanım farkı (kanal SQL'i, NETTOTAL)", "ÖLÇÜM", portal_LINENET=(mk.get("total") or {}).get("ytdCiro"), kayitli_sql_NETTOTAL=b)


def api_checks(fr: dict, m: dict) -> None:
    base = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8795").rstrip("/")
    cookie = os.environ.get("TIMAS_COOKIE", "")
    if not cookie:
        record("A API", "DOĞRULANAMADI", neden="TIMAS_COOKIE yok")
        return

    def call(method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method, headers={
            "Cookie": cookie, "Content-Type": "application/json", "X-Semantic-Caller": os.environ.get("SEMANTIC_CALLER_TOKEN", "")})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    s, j = call("GET", "/api/v1/pazar/freshness")
    record("A1 /freshness", "OK" if s == 200 and j["records"] == fr["records"] and j["lastChange"] == fr["lastChange"] else "FARK",
           status=s, api=(j or {}).get("records"), portal=fr["records"])
    s, j = call("GET", "/api/v1/pazar/matrix")
    ok = s == 200 and [(r["yayinevi"], r["medyan"]) for r in j["rows"][:5]] == [(r["yayinevi"], r["medyan"]) for r in m["rows"][:5]]
    record("A2 /matrix ilk 5 yayınevi", "OK" if ok else "FARK", status=s)
    # Geçersiz gövdeli yazma denemeleri: kayıt açmadan 400/422 dönmeli.
    for method, path, body in (("POST", "/api/v1/pazar/category-map/decision", {}),
                               ("POST", "/api/v1/pazar/briefs/draft?donem=2026-13", {}),
                               ("POST", "/api/v1/pazar/figures/yok/decision", {"karar": "uydurma"}),
                               ("POST", "/api/v1/pazar/watchlist", {"yayinevi": ""})):
        s, j = call(method, path, body)
        record(f"A3 geçersiz yazma {path}", "OK" if s in (400, 403, 404, 422) else "FARK", status=s, cevap=j)


def finish(args) -> int:
    Path(args.out).write_text(json.dumps({"tarih": date.today().isoformat(), "sonuclar": RESULTS}, ensure_ascii=False, indent=2, default=str))
    counts: dict[str, int] = {}
    for r in RESULTS:
        counts[r["durum"]] = counts.get(r["durum"], 0) + 1
    print(json.dumps(counts, ensure_ascii=False))
    return 1 if counts.get("FARK") else 0


if __name__ == "__main__":
    sys.exit(main())
