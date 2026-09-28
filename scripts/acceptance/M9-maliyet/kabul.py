#!/usr/bin/env python3
"""M9 birim maliyet sağlayıcısı (M32 / M33 / M53 bağı) — test sunucusunda gerçek kayıt, gerçek M9 görüntüsü ve Logo ile kabul.

Yalnız okur: analiz açmaz, imza atmaz, Logo'ya ve CRM'e yazmaz. Önce M9 görüntüsü en az bir kez kurulmuş olmalı
(Fiyatlama ekranı açılınca ya da `POST /api/v1/pricing/refresh`).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M9-maliyet/kabul.py --out /tmp/claude-<oturum>/m9-maliyet-kabul.json

Kontroller (OK / FARK / DOĞRULANAMADI):
- K1  onaylı analizi olan her kitap (en çok --ornek): sağlayıcı «onayli-analiz» ve maliyet = kaydın
      `result_json.summary.unitCost`'u (bağımsız SQL, referans.sql R1).
- K2  onaylı analizi olmayan, görüntüde maliyetli satışı olan --ornek kitap: sağlayıcı «gerceklesen» ve maliyet = Logo'da
      aynı yıl, aynı kopyada `SUM(AMOUNT × OUTCOST) ÷ SUM(AMOUNT)` (OUTCOST > 0) (R2). En az 5 kitap.
- K3  satışı olup maliyeti hiç girilmemiş --ornek kitap: sağlayıcı «yok», maliyet None; Logo'da da OUTCOST > 0 satış yok (R3).
- K4  hiç var olmayan stok kodu: «yok» + «maliyet bilinmiyor».
- K5  bağ biçimleri: M32 `corporate_sales_sources.unit_costs(…, "m9")` ve M33 `tenders_sources.unit_costs(…)` aynı
      sağlayıcıyla aynı sayıyı veriyor; M53 main'deyse o da.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge import corporate_sales_sources as CS  # noqa: E402
from semantic_bridge import tenders_sources as TS  # noqa: E402
from semantic_bridge.pricing import cost_provider as CP  # noqa: E402
from semantic_bridge.pricing import data as D  # noqa: E402
from semantic_bridge.pricing import store as S  # noqa: E402
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


def copy_for(snap: dict, year: int) -> tuple[str, str, str] | None:
    """Görüntünün o yılı okuduğu kopya ve yılla kesişen [başlangıç, bitiş) aralığı."""
    for c in snap.get("copies") or []:
        a, b = max(c["from"], f"{year}-01-01"), min(c["to"], f"{year + 1}-01-01")
        if a < b:
            return c["firm"], a, b
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="m9-maliyet-kabul.json")
    ap.add_argument("--ornek", type=int, default=5, help="kontrol başına kitap sayısı (en az 5)")
    args = ap.parse_args()
    n = max(5, args.ornek)

    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    S.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    snap = D.Store(lambda name: None).get()
    record("M9 görüntüsü var mı", "OK" if snap else "DOĞRULANAMADI",
           dataEnd=(snap or {}).get("dataEnd"), asOf=(snap or {}).get("asOf"))
    provider = CP.Provider(engine=lambda: engine, tenant=lambda: tenant, snapshot=lambda: snap)
    logo = bsrc.runner(os.environ["SEMANTIC_CONNECTION_FILE"])

    # K1 — onaylı analiz (R1: bağımsız SQL, kaydın dondurulmuş sonucu)
    with engine.connect() as c:
        rows = c.execute(sa.text(
            "SELECT stock_code, stage, result_json FROM semantic_pricing_analyses "
            "WHERE tenant_id = :t AND status = 'onaylandi' AND stock_code IS NOT NULL"), {"t": tenant}).mappings().all()
    approved: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        try:
            u = (json.loads(r["result_json"] or "{}").get("summary") or {}).get("unitCost")
        except ValueError:
            u = None
        if u and float(u) > 0:
            approved.setdefault(r["stock_code"], []).append((r["stage"], float(u)))
    if not approved:
        record("K1 onaylı analiz maliyeti", "DOĞRULANAMADI", neden="bu kurulumda onaylı ve stok kodlu analiz yok")
    got = provider.unit_costs(list(approved)[:n])
    for code, cands in list(approved.items())[:n]:
        g = got[code]
        ok = g["kaynak"] == "onayli-analiz" and any(close(g["maliyet"], u) for _, u in cands)
        record(f"K1 onaylı analiz {code}", "OK" if ok else "FARK", saglayici=g, kayit=cands)

    # K2 — gerçekleşen (R2: aynı yıl ve kopyada Logo'dan bağımsız hesap)
    sales = (snap or {}).get("sales") or {}
    candidates = [code for code, ys in sales.items() if code not in approved
                  and any((v or {}).get("costedQty", 0) > 0 for v in ys.values())]
    candidates.sort(key=lambda code: -max(float((v or {}).get("costedQty") or 0) for v in sales[code].values()))
    got = provider.unit_costs(candidates[:n])
    if len(candidates) < 5:
        record("K2 gerçekleşen örnek sayısı", "DOĞRULANAMADI", bulunan=len(candidates))
    for code in candidates[:n]:
        g = got[code]
        rng = copy_for(snap, g.get("yil") or 0) if g.get("yil") else None
        if g["kaynak"] != "gerceklesen" or not rng:
            record(f"K2 gerçekleşen {code}", "FARK", saglayici=g, neden="kaynak gerceklesen değil ya da kopya yok")
            continue
        firm, a, b = rng
        ref = logo(f"""SELECT SUM(S.AMOUNT * S.OUTCOST) / NULLIF(SUM(S.AMOUNT), 0) AS birim
FROM dbo.LG_{firm}_01_STLINE S JOIN dbo.LG_{firm}_ITEMS IT ON IT.LOGICALREF = S.STOCKREF
WHERE IT.CODE = N'{q(code)}' AND S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7, 8, 9)
  AND S.OUTCOST > 0 AND S.DATE_ >= '{a.replace('-', '')}' AND S.DATE_ < '{b.replace('-', '')}'""")[0]["birim"]
        record(f"K2 gerçekleşen {code} ({g['yil']})", "OK" if close(g["maliyet"], ref) else "FARK",
               saglayici=g["maliyet"], referans=ref, firma=firm, aralik=[a, b])

    # K3 — satışı var, maliyeti hiç girilmemiş (R3)
    uncosted = [code for code, ys in sales.items() if code not in approved
                and all(float((v or {}).get("costedQty") or 0) <= 0 for v in ys.values())
                and any(float((v or {}).get("soldQty") or 0) > 0 for v in ys.values())][:n]
    if not uncosted:
        record("K3 maliyetsiz kitap", "DOĞRULANAMADI", neden="görüntüde maliyeti girilmemiş satış yok")
    got = provider.unit_costs(uncosted)
    for code in uncosted:
        g = got[code]
        refs = []
        for c in (snap or {}).get("copies") or []:
            refs.append(logo(f"""SELECT COUNT(*) AS v FROM dbo.LG_{c['firm']}_01_STLINE S
JOIN dbo.LG_{c['firm']}_ITEMS IT ON IT.LOGICALREF = S.STOCKREF
WHERE IT.CODE = N'{q(code)}' AND S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7, 8, 9)
  AND S.OUTCOST > 0 AND S.DATE_ >= '{c['from'].replace('-', '')}' AND S.DATE_ < '{c['to'].replace('-', '')}'""")[0]["v"])
        ok = g["kaynak"] == "yok" and g["maliyet"] is None and sum(int(x or 0) for x in refs) == 0
        record(f"K3 maliyet bilinmiyor {code}", "OK" if ok else "FARK", saglayici=g, logo_maliyetli_satir=refs)

    # K4 — var olmayan kod
    g = provider.unit_costs(["KABUL-YOK-000"])["KABUL-YOK-000"]
    record("K4 olmayan kod", "OK" if g == {"maliyet": None, "kaynak": "yok", "tarih": None, "not": "maliyet bilinmiyor"}
           else "FARK", saglayici=g)

    # K5 — modüllerin aldığı biçim (aynı sağlayıcı, aynı sayı)
    sample = (list(approved)[:2] + candidates[:3]) or ["KABUL-YOK-000"]
    base = provider.unit_costs(sample)
    CS.register_cost_provider(provider.birim)
    try:
        corp = CS.unit_costs(sample, "m9")
    finally:
        CS.register_cost_provider(None)  # betik kendi sürecinde; köprünün bağına dokunmaz
    tend = TS.unit_costs(provider.labelled(), sample)
    for code in sample:
        want = base[code]["maliyet"]
        ok = (close(corp[code]["birim"], want) if want is not None else corp[code]["birim"] is None) and \
             ((code in tend and close(tend[code]["maliyet"], want)) if want is not None else code not in tend)
        record(f"K5 M32/M33 biçimi {code}", "OK" if ok else "FARK", saglayici=want, m32=corp[code], m33=tend.get(code))
    try:
        from semantic_bridge import sets_sources  # M53 main'e girdiyse
        sets_sources.register_cost_provider(provider.birim)
        try:
            sets = sets_sources.unit_costs(sample, "m9")
        finally:
            sets_sources.register_cost_provider(None)
        for code in sample:
            want = base[code]["maliyet"]
            ok = close(sets[code]["birim"], want) if want is not None else sets[code]["birim"] is None
            record(f"K5 M53 biçimi {code}", "OK" if ok else "FARK", saglayici=want, m53=sets[code])
    except ImportError:
        record("K5 M53 biçimi", "DOĞRULANAMADI", neden="M53 (sets_sources) bu kaynakta yok")
    return finish(args)


def finish(args) -> int:
    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
    bad = [r for r in RESULTS if r["durum"] == "FARK"]
    print(f"\n{len(RESULTS)} kontrol, {len(bad)} FARK → {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
