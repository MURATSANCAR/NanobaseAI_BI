"""G5 · M34 E-ticaret sorgu bilgisi kabulü (yalnız okuma). `kabul_g5.py` çağırır; ortam `kabul.py` ile aynı.

K1–K3 her uçta; doğrudan SQL referansları:
  E1  «Açık fark» kartı = portalda doğrudan sayım (durum açık/sonra);
  E2  pazar yerleri: gösterilen Logo sorgularının bu yılki Σ (satış − iade) = ekrandaki toplam net.
"""
from __future__ import annotations

import sqlalchemy as sa

import kabul as KB
from semantic_bridge import eticaret_kaynak as K


def kabul(heavy: bool) -> None:
    st, ov = KB.http("/api/v1/eticaret/overview")
    if st != 200:
        KB.check("e-ticaret /overview", False, f"HTTP {st}")
        return
    k = KB.contract("e-ticaret /overview", ov, K.NOT_RAKAM)
    KB.run_all("e-ticaret /overview", k, heavy)
    with KB.portal().connect() as c:
        ref = c.execute(sa.text("SELECT COUNT(*) FROM semantic_eticaret_diffs WHERE durum IN ('acik', 'sonra')")).scalar()
    KB.check("E1 e-ticaret: «Açık fark» = doğrudan sayım", int(ref or 0) == int(ov["gostergeler"]["acikFark"]),
             f"portal {ref} · ekran {ov['gostergeler']['acikFark']}")
    st, lst = KB.http("/api/v1/eticaret/diffs")
    k = KB.contract("e-ticaret /diffs", lst, K.NOT_RAKAM)
    KB.run_all("e-ticaret /diffs", k, heavy)
    if lst.get("items"):
        d = lst["items"][0]
        for path in (f"/api/v1/eticaret/diffs/{d['id']}", f"/api/v1/eticaret/items/{d['productKey']}"):
            st, out = KB.http(path)
            KB.run_all(f"e-ticaret {path.rsplit('/', 2)[-2]}", KB.contract(f"e-ticaret {path.rsplit('/', 2)[-2]}", out, K.NOT_RAKAM), heavy)
    for path in ("/api/v1/eticaret/funnel", "/api/v1/eticaret/proposals"):
        st, out = KB.http(path)
        KB.run_all(f"e-ticaret {path}", KB.contract(f"e-ticaret {path}", out, K.NOT_RAKAM), heavy)
    st, m = KB.http("/api/v1/eticaret/marketplaces", 1800)
    if st != 200:
        KB.check("e-ticaret /marketplaces", None, f"HTTP {st} (Logo bağlantısı)")
        return
    k = KB.contract("e-ticaret /marketplaces", m, K.NOT_RAKAM)
    got = KB.run_all("e-ticaret /marketplaces", k, heavy)
    rows = [r for sid, rs in got.items() if k["sources"][sid]["connection"] == "logo" and "YEAR(S.DATE_)" in k["sources"][sid]["sql"]
            for r in rs]
    if rows:
        net = sum(KB.num(r.get("satis")) - KB.num(r.get("iade")) for r in rows if int(r.get("yil") or 0) == int(m["yil"]))
        KB.check("E2 pazar yeri: Logo Σ (satış − iade) = ekrandaki net", abs(net - KB.num(m["toplam"]["net"])) < 1,
                 f"Logo {net:,.2f} · ekran {KB.num(m['toplam']['net']):,.2f}")
    for path in ("/api/v1/eticaret/marketplaces/stock-risk",):
        st, out = KB.http(path, 1800)
        KB.run_all(f"e-ticaret {path}", KB.contract(f"e-ticaret {path}", out, K.NOT_RAKAM), heavy)
    if m.get("cariler"):
        st, out = KB.http(f"/api/v1/eticaret/marketplaces/{m['cariler'][0]['kod']}/books", 1800)
        KB.run_all("e-ticaret cari kitapları", KB.contract("e-ticaret cari kitapları", out, K.NOT_RAKAM), heavy)
