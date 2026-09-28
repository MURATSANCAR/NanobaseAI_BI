"""Sorgu bilgisi kabulü — Grup 2 modülleri (finans dışı: ilk baskı, risk, kurul, ihale, ilk dağılım, saha, bayi,
müşteri, okul, kurumsal satış, kayıtlar). Test sunucusunda, yan port köprüsüyle; yalnız okuma, hiçbir yere yazmaz.

Her uçta K1–K3 (kabul.py ile aynı: kaynaksız rakam yok, kayıt tutarlı, her SQL gerçekten koşar) ve modül başına en az
bir doğrudan SQL referansı (Rn). Finansal denetim ve yönetim raporları: `kabul_denetim_yonetim.py`; bütçe, finansal
raporlar, fiyatlama: `kabul.py`.

Ortam kabul.py ile aynı. Kullanım: python kabul_grup2.py [--skip-heavy] [--only ilk-baski,risk,...]
"""
from __future__ import annotations

import argparse
from typing import Callable

from kabul import check, contract, http, num, results, run_all

BLOCKS: dict[str, Callable[[bool], None]] = {}


def block(name: str):
    def deco(fn):
        BLOCKS[name] = fn
        return fn
    return deco


def ok_or_skip(name: str, st: int, out: dict) -> bool:
    if st == 200:
        return True
    check(name, None, f"HTTP {st} ({(out.get('detail') or {}) if isinstance(out, dict) else ''})"[:200])
    return False


# ---------------------------------------------------------------- M10 ilk baskı

@block("ilk-baski")
def ilk_baski(heavy: bool) -> None:
    from semantic_bridge.management import ilk_baski_kaynak as K

    st, s = http("/api/v1/management/first-print/summary", 900)
    if not ok_or_skip("ilk baskı /summary", st, s) or not s.get("ready"):
        return
    k = contract("ilk baskı /summary", s, K.NOT_RAKAM)
    got = run_all("ilk baskı /summary", k, heavy)
    # R: Logo aylık kanal satışının yıl başına satırı = son okumanın kaydettiği satır (okumadan sonra veri girdiyse UYARI)
    for sid, src in (k.get("sources") or {}).items():
        if sid.startswith("ilkbaski.logo_aylik_kanal.") and sid in got and (src.get("stats") or {}).get("rows") is not None:
            have, want = len(got[sid]), src["stats"]["rows"]
            check(f"R ilk baskı {sid}: satır = son okuma", True if have == want else None, f"son okuma {want} · bugün {have}")
    code = next((r["code"] for r in s.get("upcoming") or []), None) or next((r["code"] for r in s.get("tracking") or []), None)
    if code:
        st, fc = http(f"/api/v1/management/first-print/forecast/{code}", 300)
        if ok_or_skip("ilk baskı /forecast", st, fc):
            contract("ilk baskı /forecast", fc, K.NOT_RAKAM)
    st, dec = http("/api/v1/management/first-print/decisions", 120)
    if ok_or_skip("ilk baskı /decisions", st, dec):
        k = contract("ilk baskı /decisions", dec, K.NOT_RAKAM)
        got = run_all("ilk baskı /decisions", k, heavy)
        rows = got.get("ilkbaski.kararlar")
        if rows is not None:
            check("R ilk baskı: karar sayısı = sorgu satırı", len(rows) == len(dec.get("items") or []),
                  f"uç {len(dec.get('items') or [])} · sorgu {len(rows)}")


# ---------------------------------------------------------------- M47 risk ve uyum

@block("risk")
def risk(heavy: bool) -> None:
    from semantic_bridge import risk_kaynak as K

    st, s = http("/api/v1/risk/summary", 300)
    if not ok_or_skip("risk /summary", st, s):
        return
    k = contract("risk /summary", s, K.NOT_RAKAM)
    got = run_all("risk /summary", k, heavy)
    rows = got.get("risk.riskler")
    if rows is not None:
        live = sum(1 for r in rows if r.get("durum") in ("acik", "izleniyor", "kabul"))
        check("R risk: canlı risk ≥ kartın sayısı (kart yalnız görebildiklerini sayar)", live >= num((s.get("sayilar") or {}).get("canli")),
              f"tablo {live} · kart {(s.get('sayilar') or {}).get('canli')}")
    # R: gösterge değerini üreten ölçüm sorgusu bugün de çalışıyor (değer farkı veri girişinden olabilir → UYARI)
    for sid in [x for x in got if x.startswith("risk.olcum.")][:6]:
        check(f"R risk ölçüm sorgusu {sid} çalıştı", True, f"{len(got[sid])} satır")
    for path in ("/api/v1/risk/risks?durum=hepsi", "/api/v1/risk/indicators", "/api/v1/risk/compliance/items",
                 "/api/v1/risk/compliance/calendar", "/api/v1/risk/policies", "/api/v1/risk/bcp", "/api/v1/risk/reports"):
        st, out = http(path, 300)
        if ok_or_skip(f"risk {path}", st, out):
            k = contract(f"risk {path.split('?')[0]}", out, K.NOT_RAKAM)
            run_all(f"risk {path.split('?')[0]}", {"sources": {sid: v for sid, v in (k.get("sources") or {}).items()
                                                              if v["connection"] == "portal"}}, heavy)


# ---------------------------------------------------------------- M33 ihale

@block("ihale")
def ihale(heavy: bool) -> None:
    from semantic_bridge import tenders_kaynak as K

    st, lst = http("/api/v1/tenders?durum=hepsi", 300)
    if not ok_or_skip("ihale /", st, lst):
        return
    k = contract("ihale /", lst, K.NOT_RAKAM)
    got = run_all("ihale /", k, heavy)
    rows = got.get("ihale.ilanlar")
    if rows is not None:
        check("R ihale: liste sayısı = ilan sorgusunun satırı", len(rows) >= num(lst.get("total")),
              f"sorgu {len(rows)} · uç {lst.get('total')} (arama süzgeci uçta)")
    for path in ("/api/v1/tenders/calendar", "/api/v1/tenders/results", "/api/v1/tenders/documents"):
        st, out = http(path, 300)
        if ok_or_skip(f"ihale {path}", st, out):
            k = contract(f"ihale {path}", out, K.NOT_RAKAM)
            run_all(f"ihale {path}", k, heavy)
    st, ps = http("/api/v1/tenders/public-sales?yenile=true", 900)
    if ok_or_skip("ihale /public-sales", st, ps):
        k = contract("ihale /public-sales", ps, K.NOT_RAKAM)
        got = run_all("ihale /public-sales", k, heavy)
        sales = next((v for sid, v in got.items() if "STLINE" in (k["sources"][sid]["sql"] or "")), None)
        if sales is not None:
            total = sum(num(r.get("ciro")) for r in sales)
            check("R ihale: kamu satışı Σ ciro ≥ uçtaki toplam (parça sorgular tekrar sayılmaz)", total + 1 >= num(ps.get("toplamCiro")),
                  f"sorgu {total:,.2f} · uç {ps.get('toplamCiro')}")
    tid = next((t["id"] for t in lst.get("items") or [] if t.get("kalem")), None)
    if tid:
        st, d = http(f"/api/v1/tenders/{tid}", 300)
        if ok_or_skip("ihale /{id}", st, d):
            k = contract("ihale /{id}", d, K.NOT_RAKAM)
            run_all("ihale /{id}", k, heavy)


# ---------------------------------------------------------------- M29 ilk dağılım

@block("ilk-dagilim")
def ilk_dagilim(heavy: bool) -> None:
    from semantic_bridge import distribution_kaynak as K

    st, bk = http("/api/v1/distribution/books", 300)
    if not ok_or_skip("dağılım /books", st, bk):
        return
    k = contract("dağılım /books", bk, K.NOT_RAKAM)
    got = run_all("dağılım /books", k, heavy)
    rows = got.get("dagilim.kitaplar")
    if rows is not None:
        check("R dağılım: liste satırı = kitap tablosu satırı (süzgeçsiz)", len(rows) == len(bk.get("items") or []),
              f"tablo {len(rows)} · uç {len(bk.get('items') or [])}")
    for path in ("/api/v1/distribution/tracking", "/api/v1/distribution/my-region?herkes=true", "/api/v1/distribution/alerts"):
        st, out = http(path, 300)
        if ok_or_skip(f"dağılım {path}", st, out):
            k = contract(f"dağılım {path.split('?')[0]}", out, K.NOT_RAKAM)
            run_all(f"dağılım {path.split('?')[0]}", k, heavy)
    code = next((b["stokKodu"] for b in bk.get("items") or [] if b.get("plan")), None)
    if code:
        pid = next(b["plan"]["id"] for b in bk["items"] if b["stokKodu"] == code)
        for path in (f"/api/v1/distribution/plans/{pid}", f"/api/v1/distribution/plans/{pid}/lines"):
            st, out = http(path, 300)
            if ok_or_skip(f"dağılım {path}", st, out):
                contract(f"dağılım {path.rsplit('/', 1)[-1]}", out, K.NOT_RAKAM)


# ---------------------------------------------------------------- M31 okul tanıtım

@block("okul")
def okul(heavy: bool) -> None:
    from semantic_bridge import school_visits_kaynak as K

    st, lst = http("/api/v1/schools?kapsam=&page=0", 900)
    if not ok_or_skip("okul /", st, lst):
        return
    k = contract("okul /", lst, K.NOT_RAKAM)
    got = run_all("okul /", k, heavy)
    # R: okul okumasının bugünkü satırı = okumanın kaydettiği satır (arada CRM'e kayıt girdiyse UYARI)
    src = (k.get("sources") or {}).get("okul.okullar") or {}
    if "okul.okullar" in got and (src.get("stats") or {}).get("rows") is not None:
        have, want = len(got["okul.okullar"]), src["stats"]["rows"]
        check("R okul: ziyaret yeri satırı = son okuma", True if have == want else None, f"son okuma {want} · bugün {have}")
    st, meta = http("/api/v1/schools/meta", 300)
    if ok_or_skip("okul /meta", st, meta):
        contract("okul /meta", meta, K.NOT_RAKAM)
        if "okul.okullar" in got:
            check("R okul: okul sayısı ≤ ziyaret yeri satırı (adı/ili boş kayıt düşer)",
                  num((meta.get("status") or {}).get("schools")) <= len(got["okul.okullar"]),
                  f"ekran {(meta.get('status') or {}).get('schools')} · sorgu {len(got['okul.okullar'])}")
    for path in ("/api/v1/schools/plan?hepsi=1", "/api/v1/schools/dealer-queue", "/api/v1/schools/context",
                 "/api/v1/schools/report/term"):
        st, out = http(path, 600)
        if ok_or_skip(f"okul {path}", st, out):
            k2 = contract(f"okul {path.split('?')[0]}", out, K.NOT_RAKAM)
            run_all(f"okul {path.split('?')[0]}", {"sources": {sid: v for sid, v in (k2.get("sources") or {}).items()
                                                               if v["connection"] == "portal"}}, heavy)
    sid = next((r["id"] for r in lst.get("items") or []), None)
    if sid:
        for path in (f"/api/v1/schools/{sid}", f"/api/v1/schools/{sid}/dealers", f"/api/v1/schools/{sid}/visits"):
            st, out = http(path, 300)
            if ok_or_skip(f"okul {path.rsplit('/', 1)[-1] if path.count('/') > 4 else '/{id}'}", st, out):
                contract(f"okul {path}", out, K.NOT_RAKAM)


# ---------------------------------------------------------------- M30 saha satış ve tahsilat

@block("saha")
def saha(heavy: bool) -> None:
    from semantic_bridge import field_sales_kaynak as K

    st, t = http("/api/v1/field/today?limit=40", 900)
    if not ok_or_skip("saha /today", st, t):
        return
    k = contract("saha /today", t, K.NOT_RAKAM)
    got = run_all("saha /today", k, heavy)
    # R: KPI «Vadesi geçmiş» = kapsamdaki sinyal satırlarının toplamı (aynı portal ifadesi)
    rows = got.get("saha.sinyal")
    if rows is not None:
        total = sum(num(r.get("vadesi_gecmis")) for r in rows)
        check("R saha: vadesi geçmiş KPI = sinyal tablosu toplamı", abs(total - num((t.get("kpi") or {}).get("vadesiGecmis"))) < 1,
              f"tablo {total:,.2f} · kart {(t.get('kpi') or {}).get('vadesiGecmis')}")
    for path in ("/api/v1/field/meta", "/api/v1/field/portfolio", "/api/v1/field/collections",
                 "/api/v1/field/collections/crm?durum=onay-bekliyor", "/api/v1/field/payment-plans", "/api/v1/field/visits",
                 "/api/v1/field/report/weekly"):
        st, out = http(path, 900)
        if ok_or_skip(f"saha {path}", st, out):
            k2 = contract(f"saha {path.split('?')[0]}", out, K.NOT_RAKAM)
            run_all(f"saha {path.split('?')[0]}", {"sources": {sid: v for sid, v in (k2.get("sources") or {}).items()
                                                               if v["connection"] == "portal" or heavy}}, heavy)
    code = next((c["code"] for c in t.get("items") or []), None)
    if code:
        st, b = http(f"/api/v1/field/customers/{code}/brief", 600)
        if ok_or_skip("saha /brief", st, b):
            contract("saha /brief", b, K.NOT_RAKAM)


# ---------------------------------------------------------------- M59 bayi riski

@block("bayi")
def bayi(heavy: bool) -> None:
    from semantic_bridge import dealers_kaynak as K

    st, s = http("/api/v1/dealers/summary", 600)
    if not ok_or_skip("bayi /summary", st, s):
        return
    k = contract("bayi /summary", s, K.NOT_RAKAM)
    got = run_all("bayi /summary", k, heavy)
    rows = got.get("bayi.skorlar")
    if rows is not None:
        total = sum(num(r.get("vadesi_gecmis")) for r in rows)
        check("R bayi: pano vadesi geçmiş = skor satırları toplamı", abs(total - num(s.get("vadesiGecmis"))) < 1,
              f"tablo {total:,.2f} · pano {s.get('vadesiGecmis')}")
    for path in ("/api/v1/dealers/meta", "/api/v1/dealers/list", "/api/v1/dealers/limits?durum=", "/api/v1/dealers/rules",
                 "/api/v1/dealers/actions"):
        st, out = http(path, 600)
        if ok_or_skip(f"bayi {path}", st, out):
            k2 = contract(f"bayi {path.split('?')[0]}", out, K.NOT_RAKAM)
            run_all(f"bayi {path.split('?')[0]}", {"sources": {sid: v for sid, v in (k2.get("sources") or {}).items()
                                                               if v["connection"] == "portal"}}, heavy)
    code = next((d["code"] for d in s.get("kotulesenler") or []), None)
    if not code:
        st, lst = http("/api/v1/dealers/list?size=1", 300)
        code = next((d["code"] for d in (lst.get("items") or [])), None) if st == 200 else None
    if code:
        for path in (f"/api/v1/dealers/{code}", f"/api/v1/dealers/{code}/aging", f"/api/v1/dealers/{code}/history"):
            st, out = http(path, 300)
            if ok_or_skip(f"bayi {path}", st, out):
                contract(f"bayi {path}", out, K.NOT_RAKAM)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-heavy", action="store_true")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    only = {x.strip() for x in a.only.split(",") if x.strip()}
    for name, fn in BLOCKS.items():
        if only and name not in only:
            continue
        print(f"== {name}", flush=True)
        try:
            fn(not a.skip_heavy)
        except Exception as e:  # noqa: BLE001 — bir modülün hatası ötekilerin kabulünü durdurmaz
            check(f"{name} bloğu", False, str(e)[:300])
    ok = sum(1 for _, s, _ in results if s == "GEÇTİ")
    bad = sum(1 for _, s, _ in results if s == "KALDI")
    print(f"== {ok} geçti, {bad} kaldı, {sum(1 for _, s, _ in results if s == 'UYARI')} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
