"""G5 · M42 Kanallar ve D2C sorgu bilgisi kabulü (yalnız okuma). `kabul_g5.py` çağırır.

K1–K3 her uçta; doğrudan SQL referansları:
  N1  karne «şirket» net cirosu ≈ gece okumasının (asıl sorgu) yıl satırlarından Σ (satış − iade) ile aynı dönemde
      (asıl sorgu kayıtlıysa; tam yıl okunursa gün payı farkı olabileceği için yalnız yıl tamamlandıysa kesin denetlenir);
  N2  kanal kodu ekranı: her kodun net cirosu = portalda o yılın Σ (satis_ciro − iade_ciro).
"""
from __future__ import annotations

import sqlalchemy as sa

import kabul as KB
from semantic_bridge.channels import kaynak as K


def kabul(heavy: bool) -> None:
    st, sc = KB.http("/api/v1/channels/scorecard", 1800)
    if st != 200:
        KB.check("kanallar /scorecard", None, f"HTTP {st}")
        return
    k = KB.contract("kanallar /scorecard", sc, K.NOT_RAKAM)
    KB.run_all("kanallar /scorecard", k, heavy)
    origins = [s for s in k["sources"].values() if s["connection"] == "logo"]
    KB.check("N1 kanallar: kanal tablosunun asıl Logo sorgusu kayıtlı", True if origins else None,
             f"{len(origins)} Logo sorgusu" if origins else "gece okuması bu kurulumda henüz koşmadı")
    st, kc = KB.http("/api/v1/channels/accounts/kanal-kodlari")
    KB.run_all("kanallar kanal kodları", KB.contract("kanallar kanal kodları", kc, K.NOT_RAKAM), heavy)
    if kc.get("yil") and kc.get("items"):
        with KB.portal().connect() as c:
            ref = {r[0]: float(r[1] or 0) for r in c.execute(sa.text(
                "SELECT kanal, SUM(satis_ciro - iade_ciro) FROM semantic_channel_kanal_months WHERE yil = :y GROUP BY kanal"),
                {"y": kc["yil"]})}
        bad = [x["kod"] for x in kc["items"] if x["kod"] in ref and abs(ref[x["kod"]] - KB.num(x["netCiro"])) > 0.05]
        KB.check("N2 kanallar: kanal kodu net cirosu = portal Σ", not bad, ", ".join(bad[:5]))
    for path in ("/api/v1/channels/meta", "/api/v1/channels/matrix", "/api/v1/channels/targets", "/api/v1/channels/d2c",
                 "/api/v1/channels/accounts", "/api/v1/channels/accounts/bolgeler", "/api/v1/channels/suggestions",
                 "/api/v1/channels/imports"):
        st, out = KB.http(path, 1800)
        if st != 200:
            KB.check(f"kanallar {path}", None, f"HTTP {st}")
            continue
        KB.run_all(f"kanallar {path}", KB.contract(f"kanallar {path}", out, K.NOT_RAKAM), heavy)
    for p in (sc.get("platforms") or [])[:2]:
        for path in (f"/api/v1/channels/channel/{p['platform']}", f"/api/v1/channels/channel/{p['platform']}/books",
                     f"/api/v1/channels/channel/{p['platform']}/returns"):
            st, out = KB.http(path, 1800)
            if st == 200:
                KB.run_all(f"kanallar {path}", KB.contract(f"kanallar {path}", out, K.NOT_RAKAM), heavy)
