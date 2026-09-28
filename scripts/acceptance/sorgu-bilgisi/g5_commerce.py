"""G5 · H3 E-ticaret müşterileri sorgu bilgisi kabulü (yalnız okuma; kişisel veri kayda girmez). `kabul_g5.py` çağırır.

K1–K3 her uçta; doğrudan SQL referansları:
  H1  özet (bu ay): «Sipariş» = portalda dönem içindeki geçerli sipariş sayısı;
  H2  segment toplamı = müşteri tablosunun satır sayısı;
  H3  hiçbir kaynak kaydında «@» yok (e-posta biçimli değer kayda girmez).
"""
from __future__ import annotations

import json

import sqlalchemy as sa

import kabul as KB
from semantic_bridge import commerce_kaynak as CK


def kabul(heavy: bool) -> None:
    st, ov = KB.http("/api/v1/commerce/overview?period=ay")
    if st != 200:
        KB.check("commerce /overview", None, f"HTTP {st}")
        return
    k = KB.contract("commerce /overview", ov, CK.NOT_RAKAM)
    KB.run_all("commerce /overview", k, heavy)
    p = ov["period"]
    with KB.portal().connect() as c:
        n = c.execute(sa.text("SELECT COUNT(*) FROM semantic_commerce_orders WHERE valid = true AND ordered_at >= :a "
                              "AND ordered_at < CAST(:b AS date) + 1"), {"a": p["from"], "b": p["to"]}).scalar()
        cust = c.execute(sa.text("SELECT COUNT(*) FROM semantic_commerce_customers")).scalar()
    KB.check("H1 commerce: «Sipariş» = doğrudan sayım", int(n or 0) == int(ov["cur"]["siparis"]), f"{n} · {ov['cur']['siparis']}")
    KB.check("H2 commerce: segment toplamı = müşteri sayısı", int(cust or 0) == sum(s["musteri"] for s in ov.get("segments") or []))
    KB.check("H3 commerce: kayıtta e-posta yok", "@" not in json.dumps(k, default=str))
    for path in ("/api/v1/commerce/meta", "/api/v1/commerce/customers/rfm", "/api/v1/commerce/customers/moves",
                 "/api/v1/commerce/customers", "/api/v1/commerce/products/funnel", "/api/v1/commerce/triggers",
                 "/api/v1/commerce/runs", "/api/v1/commerce/campaigns", "/api/v1/commerce/segments/summary",
                 "/api/v1/commerce/triggers/new-books"):
        st, out = KB.http(path, 900)
        if st != 200:
            KB.check(f"commerce {path}", None, f"HTTP {st}")
            continue
        KB.run_all(f"commerce {path}", KB.contract(f"commerce {path}", out, CK.NOT_RAKAM), heavy)
        if path.endswith("/customers") and out.get("items"):
            st, card = KB.http(f"/api/v1/commerce/customers/{out['items'][0]['key']}")
            KB.run_all("commerce müşteri kartı", KB.contract("commerce müşteri kartı", card, CK.NOT_RAKAM), heavy)
