"""Sorgu bilgisi kabulü · M52 Tedarik ve baskı (test sunucusu, yan port köprüsü; yalnız okuma).

Her uçta K1–K3 ve doğrudan SQL referansları:
  T1  `/sources` yer tutucusuz (şablon değil çalışan metin) ve her SQL hatasız koşar;
  T2  tedarikçi bakiyesi: listedeki ilk tedarikçinin bakiyesi = Logo cari sorgusunun o cari satırındaki bakiye;
  T3  12 ay alış: ilk tedarikçinin «12 ay alış»ı ≤ Logo alış sorgusunun o cari toplamı (pencere 24 ay okunur);
  T4  depo girişi: gerçekleşen ayların toplam adedi = Logo üretimden giriş sorgusunun Σ adet (son 12 ay içinde).
"""
from __future__ import annotations

import kabul as KB
from semantic_bridge import provenance as PV
from semantic_bridge import supply_kaynak as K

B = "/api/v1/supply"


def main(heavy: bool) -> None:
    st, srcs = KB.http(f"{B}/sources", 1800)
    if st != 200:
        KB.check("tedarik /sources", False, f"HTTP {st}")
        return
    left = [s["id"] for s in srcs.get("sources") or [] if PV.placeholders_left(s.get("sql") or "")]
    KB.check("T1 tedarik: /sources şablon değil çalışan metin", bool(srcs.get("sources")) and not left, ", ".join(left))
    got = KB.run_all("tedarik /sources", srcs.get("kaynaklar") or {}, heavy)
    for path in ("/overview", "/load", "/paper", "/suppliers", "/unbilled", "/incoming?aylar=6", "/suggestions",
                 "/capacity", "/payments?gun=30", "/cost-trend?kirilim=cilt"):
        st, out = KB.http(B + path, 1800)
        if st == 403:
            KB.check(f"tedarik {path}", None, "rolde yok")
            continue
        k = KB.contract(f"tedarik {path}", out, K.NOT_RAKAM)
        KB.run_all(f"tedarik {path}", {"sources": {sid: v for sid, v in (k.get("sources") or {}).items()
                                                  if v["connection"] == "portal"}}, heavy)
        if path == "/suppliers" and out.get("items") and "bakiye" in out["items"][0]:
            first = out["items"][0]
            cari = next((rows for sid, rows in got.items() if sid.startswith("tedarik.logo_tedarikci_cari")), None)
            if cari is not None:
                row = next((r for r in cari if str(r.get("kod") or "").strip() == first["kod"]), None)
                KB.check("T2 tedarik: bakiye = Logo cari sorgusu", row is not None and abs(KB.num(row.get("bakiye")) - KB.num(first["bakiye"])) < 0.05,
                         f"{first['kod']}: sorgu {row and row.get('bakiye')} · ekran {first['bakiye']}")
            alis = [r for sid, rows in got.items() if sid.startswith("tedarik.logo_alis_fatura") for r in rows
                    if str(r.get("cari_kod") or "").strip() == first["kod"]]
            if alis:
                total = sum(KB.num(r.get("tutar")) for r in alis)
                KB.check("T3 tedarik: 12 ay alış ≤ Logo alış sorgusu (24 ay)", KB.num(first.get("alis12")) <= total + 0.05,
                         f"ekran {first.get('alis12')} · sorgu {total:,.2f}")
            st2, one = KB.http(f"{B}/suppliers/{first['kod']}", 1800)
            if st2 == 200:
                KB.contract("tedarik /suppliers/{cari}", one, K.NOT_RAKAM)
        if path.startswith("/incoming"):
            giris = [r for sid, rows in got.items() if sid.startswith("tedarik.logo_uretim_giris") for r in rows]
            keys = {g["ay"] for g in out.get("gecmis") or []}
            ref = sum(KB.num(r.get("adet")) for r in giris if f"{int(r['yil']):04d}-{int(r['ay']):02d}" in keys)
            ekran = sum(KB.num(g["adet"]) for g in out.get("gecmis") or [])
            KB.check("T4 tedarik: gerçekleşen depo girişi = Logo üretimden giriş sorgusu", abs(ref - ekran) < 1,
                     f"sorgu {ref:,.0f} · ekran {ekran:,.0f}")
