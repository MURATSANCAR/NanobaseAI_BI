"""Sorgu bilgisi kabulü · M43 Depo ve stok (test sunucusu, yan port köprüsü; yalnız okuma).

Her uçta K1–K3 (`kabul.contract`, `kabul.run_all`) ve doğrudan SQL referansları:
  S1  «Toplam stok» KPI = Logo bakiye sorgusunun (çalışan metin) Σ bakiye'si, bakiyesi > 0 kitaplarda (ticari önek hariç);
  S2  «Logo'ya geçmemiş» KPI = CRM aktarım sorgusunun mesajı dolu satır sayısı;
  S3  Logo–CRM farkı: listedeki ilk kitabın farkı = CRM raf sorgusunun o kitap toplamı − Logo bakiye sorgusunun toplamı;
  S4  depo hattı: aşama sayılarının toplamı ≤ depo hattı sorgusunun satır sayısı.
Çağrı: `python g3.py` (hepsi) ya da `python -c "import g3_stock; g3_stock.main(True)"`.
"""
from __future__ import annotations

import kabul as KB
from semantic_bridge import stock_kaynak as K

B = "/api/v1/stock"


def main(heavy: bool) -> None:
    st, ov = KB.http(f"{B}/overview", 1800)
    if st != 200:
        KB.check("stok /overview", False, f"HTTP {st}")
        return
    k = KB.contract("stok /overview", ov, K.NOT_RAKAM)
    got = KB.run_all("stok /overview", k, heavy)
    bak = got.get("stok.logo_bakiye")
    if bak is not None:
        per: dict[str, float] = {}
        for r in bak:
            code = str(r.get("stok_kodu") or "").strip()
            per[code] = per.get(code, 0.0) + KB.num(r.get("bakiye"))
        total = sum(v for c, v in per.items() if v > 0 and c and not c.startswith("157"))
        KB.check("S1 stok: «Toplam stok» = Logo bakiye sorgusu Σ (> 0)", abs(total - KB.num(ov.get("toplamStok"))) < 1,
                 f"sorgu {total:,.0f} · ekran {KB.num(ov.get('toplamStok')):,.0f}")
    tr = got.get("stok.crm_aktarim_hatasi")
    if tr is not None:
        err = sum(1 for r in tr if r.get("hata") in (1, True, "1"))
        KB.check("S2 stok: «Logo'ya geçmemiş» = CRM aktarım sorgusunun hatalı satırı", err == ov.get("aktarimHatasi"),
                 f"sorgu {err} · ekran {ov.get('aktarimHatasi')}")
    for path in ("/items", "/running-out", "/excess", "/diff", "/transfer-errors", "/pick-line", "/thresholds?durum=oneri",
                 "/thresholds?durum=onayli", "/suggestions?tur=bitecek"):
        st, out = KB.http(B + path, 1800)
        if st == 403:
            KB.check(f"stok {path}", None, "rolde yok")
            continue
        kk = KB.contract(f"stok {path}", out, K.NOT_RAKAM)
        KB.run_all(f"stok {path}", {"sources": {sid: v for sid, v in (kk.get("sources") or {}).items()
                                                if v["connection"] == "portal"}}, heavy)
        if path == "/diff" and out.get("items") and bak is not None:
            first = out["items"][0]
            raf = got.get("stok.crm_raf_stok") or KB.run_sql(kk["sources"]["stok.crm_raf_stok"])[0]
            crm = sum(KB.num(r.get("kalan")) for r in raf if str(r.get("stok_kodu") or "").strip() == first["stokKodu"])
            logo = sum(KB.num(r.get("bakiye")) for r in bak if str(r.get("stok_kodu") or "").strip() == first["stokKodu"])
            KB.check("S3 stok: fark = CRM raf sorgusu − Logo bakiye sorgusu (ilk kitap)",
                     abs((crm - logo) - KB.num(first.get("fark"))) < 1, f"{first['stokKodu']}: {crm - logo:,.0f} · {first.get('fark')}")
        if path == "/pick-line" and "stok.crm_depo_hatti" in (kk.get("sources") or {}):
            rows, _ = KB.run_sql(kk["sources"]["stok.crm_depo_hatti"])
            n = sum(a["adet"] for a in out.get("asamalar") or [])
            KB.check("S4 stok: aşama sayıları ≤ depo hattı sorgusu", n <= len(rows), f"aşama {n} · sorgu {len(rows)}")
    st, lst = KB.http(f"{B}/items", 1800)
    first = (lst.get("items") or [None])[0] if st == 200 else None
    if first:
        st, it = KB.http(f"{B}/items/{first['stokKodu']}", 1800)
        KB.contract("stok /items/{kod}", it, K.NOT_RAKAM)
