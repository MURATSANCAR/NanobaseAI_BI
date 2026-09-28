"""G5 · M35 Kampanyalar sorgu bilgisi kabulü (yalnız okuma). `kabul_g5.py` çağırır.

K1–K3 her uçta; doğrudan SQL referansları:
  C1  «kitap sayısı» = portalda semantic_kampanya_books satır sayısı;
  C2  durum sayıları toplamı = portalda kampanya kaydı sayısı;
  C3  sonuç: kampanya dönemi adedi = sonuç tablosunda o kampanyanın «kampanya» dönemi Σ adet.
"""
from __future__ import annotations

import sqlalchemy as sa

import kabul as KB
from semantic_bridge import kampanya_kaynak as KK


def kabul(heavy: bool) -> None:
    st, ov = KB.http("/api/v1/kampanya/overview")
    if st != 200:
        KB.check("kampanya /overview", False, f"HTTP {st}")
        return
    k = KB.contract("kampanya /overview", ov, KK.NOT_RAKAM)
    KB.run_all("kampanya /overview", k, heavy)
    with KB.portal().connect() as c:
        books = c.execute(sa.text("SELECT COUNT(*) FROM semantic_kampanya_books")).scalar()
        camps = c.execute(sa.text("SELECT COUNT(*) FROM semantic_kampanya_campaigns")).scalar()
    KB.check("C1 kampanya: kitap sayısı = doğrudan sayım", int(books or 0) == int(ov.get("kitapSayisi") or 0), f"{books} · {ov.get('kitapSayisi')}")
    KB.check("C2 kampanya: durum sayıları toplamı = kayıt sayısı", int(camps or 0) == sum(int(v) for v in (ov.get("sayilar") or {}).values()))
    for path in ("/api/v1/kampanya/campaigns", "/api/v1/kampanya/calendar", "/api/v1/kampanya/candidates",
                 "/api/v1/kampanya/learnings", "/api/v1/kampanya/crm-campaigns"):
        st, out = KB.http(path, 1800)
        if st != 200:
            KB.check(f"kampanya {path}", None, f"HTTP {st}")
            continue
        KB.run_all(f"kampanya {path}", KB.contract(f"kampanya {path}", out, KK.NOT_RAKAM), heavy)
    st, lst = KB.http("/api/v1/kampanya/campaigns?durum=bitti,yurutuluyor,onaylandi")
    for camp in (lst.get("items") or [])[:3]:
        st, one = KB.http(f"/api/v1/kampanya/campaigns/{camp['id']}")
        KB.run_all("kampanya ayrıntı", KB.contract("kampanya ayrıntı", one, KK.NOT_RAKAM), heavy)
        st, res = KB.http(f"/api/v1/kampanya/campaigns/{camp['id']}/results")
        k = KB.contract("kampanya sonuç", res, KK.NOT_RAKAM)
        KB.run_all("kampanya sonuç", k, heavy)
        with KB.portal().connect() as c:
            ref = c.execute(sa.text("SELECT COALESCE(SUM(adet), 0) FROM semantic_kampanya_results WHERE campaign_id = :c AND donem = 'kampanya'"),
                            {"c": camp["id"]}).scalar()
        got = KB.num(((res.get("donemler") or {}).get("kampanya") or {}).get("adet"))
        KB.check("C3 kampanya sonucu: kampanya dönemi adet = doğrudan Σ", abs(KB.num(ref) - got) < 0.01, f"{ref} · {got}")
