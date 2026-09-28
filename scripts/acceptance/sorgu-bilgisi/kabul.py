"""Sorgu bilgisi kabulü (test sunucusunda, yan port köprüsü; yalnız okuma, hiçbir yere yazmaz).

Üç örnek modülün (M46 bütçe, M45 finansal raporlar, M9 fiyatlama) uçlarını çağırır ve her cevapta:
  K1  `kaynaklar` var, hata yok; cevaptaki her rakam bir kaynağa bağlı (`provenance.uncovered_numbers`);
  K2  kayıt tutarlı (`provenance.problems`), SQL'de yer tutucu, sır izi, teknoloji adı yok;
  K3  her SQL kopyala-çalıştır: Logo/CRM metni bağlantının kendisinde, portal metni portal veritabanında hatasız koşar
      (baştaki «USE [..];» satırı SSMS içindir; burada bağlantı zaten o veritabanında olduğundan atlanır);
ve doğrudan SQL referansları:
  R1  bütçe: Logo satış sorgusunun Σ ciro'su = portal tablosunun o yılki Σ ciro'su;
  R2  bütçe: Logo gider sorgusunun Σ tutar'ı = portal gider tablosunun o yılki Σ tutar'ı;
  R3  finans: Logo aylık satış sorgusunun Σ net'i = semantic_finance_sales_month o yılki Σ net;
  R4  finans özeti: «Net satış» kartı = kartın portal sorgusunun net kolonu;
  R5  fiyatlama: görüntüdeki Logo satış sorgularının toplam satırı = görüntünün kaydettiği satır sayısı
      (görüntüden sonra Logo'ya satış girdiyse fark beklenir; o durumda «UYARI» yazılır, kalmaz);
  R6  bütçe izleme: «Şirket satışı» gerçekleşeni ≥ plan kitaplarının gerçekleşeni (hedef dışı eklenir).

Ortam: BASE (ör. http://127.0.0.1:8798), COOKIE (timasai'nin kısa oturum çerezi), SEMANTIC_CONNECTION_FILE (Logo),
SEMANTIC_CRM_CONNECTION_FILE, SEMANTIC_STORE_DSN (portal), PYTHONPATH=<aday ağaç>/backend.
Kullanım: python kabul.py [--year 2026] [--skip-heavy]   (--skip-heavy: tam yıl Logo sorgularını koşturmaz)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request

import sqlalchemy as sa

from semantic_bridge import provenance as PV

BASE = os.environ.get("BASE", "http://127.0.0.1:8798").rstrip("/")
COOKIE = os.environ.get("COOKIE", "")
results: list[tuple[str, str, str]] = []


def http(path: str, timeout: int = 900):
    req = urllib.request.Request(BASE + path, headers={"Cookie": COOKIE})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def check(name: str, ok, detail: str = "") -> None:
    state = "GEÇTİ" if ok is True else ("UYARI" if ok is None else "KALDI")
    results.append((name, state, detail))
    print(f"{state} {name}" + (f" — {detail}" if detail else ""), flush=True)


_conns: dict[str, object] = {}


def connector(kind: str):
    if kind not in _conns:
        from semantic_layer.profiler.connectors import connector_from_file

        path = os.environ["SEMANTIC_CONNECTION_FILE"] if kind == "logo" else os.environ.get(
            "SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
        c = connector_from_file(path)
        c.query_timeout = 1800
        _conns[kind] = c
    return _conns[kind]


_engine = None


def portal():
    global _engine
    if _engine is None:
        _engine = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
    return _engine


def run_sql(src: dict) -> tuple[list[dict], int]:
    """Kaynağın SQL'ini olduğu gibi (USE satırı hariç) koşturur; satırlar ve ms."""
    text = re.sub(r"(?is)^\s*USE \[[^\]]+\];\s*", "", src["sql"])
    t = time.monotonic()
    if src["connection"] == "portal":
        with portal().connect() as c:
            rows = [dict(r._mapping) for r in c.execute(sa.text(text.replace(":", r"\:")))]
    else:
        _cols, rows, truncated = connector(src["connection"]).execute(text, 5_000_000)
        assert not truncated, "sonuç kesildi"
    return rows, int((time.monotonic() - t) * 1000)


def num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def contract(name: str, out: dict, ignore=()) -> dict:
    k = out.get("kaynaklar") or {}
    check(f"{name} · K1 kaynaklar", bool(k) and not k.get("error"), k.get("error", ""))
    left = PV.uncovered_numbers(out, ignore)
    check(f"{name} · K1 kaynaksız rakam yok", not left, ", ".join(left[:8]))
    probs = PV.problems(out)
    tech = [sid for sid, s in (k.get("sources") or {}).items() if any(
        PV._TECH.search(line) for line in s["sql"].splitlines() if line.strip().startswith("--"))]
    check(f"{name} · K2 tutarlılık, yer tutucu, sır, teknoloji adı", not probs and not tech, "; ".join(probs[:5] + tech[:5]))
    return k


def run_all(name: str, k: dict, heavy: bool) -> dict[str, list[dict]]:
    got: dict[str, list[dict]] = {}
    for sid, s in (k.get("sources") or {}).items():
        if not heavy and s["connection"] != "portal" and (s.get("stats") or {}).get("dbMs", 0) and s["stats"]["dbMs"] > 60_000:
            check(f"{name} · K3 {sid}", None, "ağır sorgu atlandı (--skip-heavy)")
            continue
        try:
            rows, ms = run_sql(s)
            got[sid] = rows
            check(f"{name} · K3 {sid} çalıştı", True, f"{len(rows)} satır, {ms} ms")
        except Exception as e:  # noqa: BLE001
            check(f"{name} · K3 {sid} çalıştı", False, str(e)[:200])
    return got


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=0)
    ap.add_argument("--skip-heavy", action="store_true")
    a = ap.parse_args()
    heavy = not a.skip_heavy

    # ---------------------------------------------------------------- M46
    from semantic_bridge import budget_kaynak as BK

    st, meta = http("/api/v1/budget/meta")
    year = a.year or int((meta.get("data") or {}).get("dataEnd", "2026")[:4])
    st, plans = http(f"/api/v1/budget/plans?year={year}")
    contract("bütçe /plans", plans, BK.NOT_RAKAM)
    st, dfl = http(f"/api/v1/budget/defaults?year={year + 1}", 1800)
    k = contract("bütçe /defaults", dfl, BK.NOT_RAKAM)
    run_all("bütçe /defaults", {"sources": {sid: v for sid, v in (k.get("sources") or {}).items()
                                           if v["connection"] == "portal"}}, heavy)
    plan = next((p for p in plans.get("items") or [] if p["status"] == "onayli"), (plans.get("items") or [None])[0])
    if plan:
        st, tr = http(f"/api/v1/budget/tracking?year={year}&plan={plan['id']}", 1800)
        k = contract("bütçe /tracking", tr, BK.NOT_RAKAM)
        got = run_all("bütçe /tracking", k, heavy)
        ls = got.get(f"logo.satis.{year}")
        if ls is not None:
            with portal().connect() as c:
                ref = c.execute(sa.text("SELECT COALESCE(SUM(ciro), 0) FROM semantic_budget_sales_actuals WHERE year = :y"),
                                {"y": year}).scalar()
            logo = sum(num(r.get("ciro")) for r in ls)
            check("R1 bütçe: Logo satış Σ ciro = portal Σ ciro", abs(logo - num(ref)) < 1, f"Logo {logo:,.2f} · portal {num(ref):,.2f}")
        lg = got.get(f"logo.gider.{year}")
        if lg is not None:
            with portal().connect() as c:
                ref = c.execute(sa.text("SELECT COALESCE(SUM(tutar), 0) FROM semantic_budget_expense_actuals WHERE year = :y"),
                                {"y": year}).scalar()
            logo = sum(num(r.get("tutar")) for r in lg)
            check("R2 bütçe: Logo gider Σ = portal Σ", abs(logo - num(ref)) < 1, f"Logo {logo:,.2f} · portal {num(ref):,.2f}")
        s, kh = tr.get("sirket") or {}, tr.get("kitapHedefleri") or {}
        if s and kh:
            check("R6 bütçe: şirket gerçekleşeni ≥ plan kitapları gerçekleşeni", num(s.get("gercekCiro")) + 0.01 >= num(kh.get("gercekCiro")))
        for path in (f"/api/v1/budget/plans/{plan['id']}/books", f"/api/v1/budget/plans/{plan['id']}/program",
                     f"/api/v1/budget/plans/{plan['id']}/departments", f"/api/v1/budget/compare?year={year}",
                     f"/api/v1/budget/deviations?year={year}"):
            st, out = http(path, 1800)
            k = contract(f"bütçe {path.split('?')[0].rsplit('/', 1)[-1]}", out, BK.NOT_RAKAM)
            run_all(f"bütçe {path.split('?')[0].rsplit('/', 1)[-1]}", {"sources": {sid: v for sid, v in k.get("sources", {}).items()
                                                                                  if v["connection"] == "portal"}}, heavy)

    # ---------------------------------------------------------------- M45
    from semantic_bridge import finance_kaynak as FK

    ig = FK.NOT_RAKAM + ("status",)
    st, summ = http("/api/v1/finance/summary", 1800)
    k = contract("finans /summary", summ, ig)
    got = run_all("finans /summary", k, heavy)
    card = next((c for c in summ.get("cards") or [] if c["id"] == "net-satis"), None)
    pr = got.get("portal.fin.satisYbd")
    if card and pr:
        net = num(list(pr[0].values())[2])  # sales_totals_stmt: adet, brut, net, …
        check("R4 finans: «Net satış» kartı = kartın portal sorgusu", abs(net - num(card["value"])) < 0.01, f"{net:,.2f} · {card['value']}")
    y = int((summ.get("veriSonu") or f"{year}")[:4])
    ls = got.get(f"logo.fin.satis.{y}")
    if ls is not None:
        with portal().connect() as c:
            ref = c.execute(sa.text("SELECT COALESCE(SUM(net), 0) FROM semantic_finance_sales_month WHERE year = :y"), {"y": y}).scalar()
        logo = sum(num(r.get("net")) for r in ls)
        check("R3 finans: Logo aylık satış Σ net = portal Σ net", abs(logo - num(ref)) < 1, f"Logo {logo:,.2f} · portal {num(ref):,.2f}")
    for path in ("/api/v1/finance/pnl", f"/api/v1/finance/profitability?year={y}", "/api/v1/finance/cash",
                 "/api/v1/finance/cash/history", f"/api/v1/finance/budget?year={y}", f"/api/v1/finance/tax-calendar?year={y}",
                 f"/api/v1/finance/account-map?year={y}"):
        st, out = http(path, 1800)
        if st == 403:
            check(f"finans {path}", None, "bu oturumun rolünde yok")
            continue
        contract(f"finans {path.split('?')[0]}", out, ig)

    # ---------------------------------------------------------------- M9
    from semantic_bridge.pricing import kaynak as PK

    ig = PK.NOT_RAKAM + ("offset", "limit", "dataEnd", "since", "until")
    st, srcs = http("/api/v1/pricing/sources")
    k = contract("fiyatlama /sources", srcs, ig)
    got = run_all("fiyatlama /sources", k, heavy)
    runs = [sid for sid in got if sid.startswith("fiyatlama.logo_satis")]
    if runs:
        want = next((s["stats"]["rows"] for s in srcs.get("sources") or [] if s["id"] == "logo_satis" and s.get("stats")), None)
        have = sum(len(got[r]) for r in runs)
        check("R5 fiyatlama: görüntünün Logo satış satırı = sorgunun bugünkü satırı", True if have == want else None,
              f"görüntü {want} · bugün {have}")
    for path in ("/api/v1/pricing/overview", "/api/v1/pricing/actuals", "/api/v1/pricing/backlist", "/api/v1/pricing/analyses",
                 "/api/v1/pricing/proposals"):
        st, out = http(path)
        contract(f"fiyatlama {path}", out, ig)

    ok = sum(1 for _, s, _ in results if s == "GEÇTİ")
    bad = sum(1 for _, s, _ in results if s == "KALDI")
    warn = sum(1 for _, s, _ in results if s == "UYARI")
    print(f"== {ok} geçti, {bad} kaldı, {warn} uyarı")
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
