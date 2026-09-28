"""Sorgu bilgisi kabulü · M44 Lojistik ve kargo (test sunucusu, yan port köprüsü; yalnız okuma).

Her uçta K1–K3 ve doğrudan SQL referansları:
  L1  «Sevk edilen» KPI = sevk sayısı sorgusunun `adet` kolonu;
  L2  «Entegrasyon hatası» ≤ hata koşullu sipariş sorgusunun satır sayısı (başarılı değerler Python'da ayıklanır);
  L3  «Toplam teslim bekleyen» ≤ kargo kaydı sorgusunun satır sayısı;
  L4  hiçbir gösterilen sorguda kargo firması kimlik kolonu ve alıcı/teslim alan kolonu yok.
"""
from __future__ import annotations

import kabul as KB
from semantic_bridge import shipping_kaynak as K
from semantic_bridge import shipping_sources as src

B = "/api/v1/shipping"


def _clean(name: str, k: dict) -> None:
    bad = [sid for sid, s in (k.get("sources") or {}).items()
           if any(c in s["sql"].lower() for c in src.FORBIDDEN_COLUMNS) or " as alici" in s["sql"].lower()]
    KB.check(f"L4 kargo {name}: kimlik/kişisel kolon yok", not bad, ", ".join(bad))


def main(heavy: bool) -> None:
    st, ov = KB.http(f"{B}/overview", 1800)
    if st != 200:
        KB.check("kargo /overview", False, f"HTTP {st}")
        return
    k = KB.contract("kargo /overview", ov, K.NOT_RAKAM)
    _clean("/overview", k)
    got = KB.run_all("kargo /overview", k, heavy)
    sevk = next((rows for sid, rows in got.items() if sid.startswith("kargo.shipped.crm_sevk_sayisi")), None)
    if sevk:
        KB.check("L1 kargo: «Sevk edilen» = sevk sayısı sorgusu", int(KB.num(sevk[0].get("adet"))) == ov["sevk"]["adet"],
                 f"sorgu {sevk[0].get('adet')} · ekran {ov['sevk']['adet']}")
    hata = next((rows for sid, rows in got.items() if sid.startswith("kargo.errors.crm_siparis_asama")), None)
    if hata is not None:
        KB.check("L2 kargo: entegrasyon hatası ≤ hata sorgusu satırı", ov["hata"] <= len(hata), f"ekran {ov['hata']} · sorgu {len(hata)}")
    kayit = next((rows for sid, rows in got.items() if sid.startswith("kargo.index.crm_kargo_bilgisi")), None)
    if kayit is not None:
        KB.check("L3 kargo: teslim bekleyen ≤ kargo kaydı sorgusu", ov["bekleyen"]["toplam"] <= len(kayit),
                 f"ekran {ov['bekleyen']['toplam']} · sorgu {len(kayit)}")
    for path in ("/errors", "/untracked", "/boxed", "/waiting", "/carriers", "/shipments", "/reconcile", "/reconcile/candidates"):
        st, out = KB.http(B + path, 1800)
        if st == 403:
            KB.check(f"kargo {path}", None, "rolde yok")
            continue
        kk = KB.contract(f"kargo {path}", out, K.NOT_RAKAM)
        _clean(path, kk)
        if path == "/shipments" and out.get("items"):
            st2, one = KB.http(f"{B}/shipments/{out['items'][0]['id']}", 1800)
            if st2 == 200:
                _clean("/shipments/{id}", KB.contract("kargo /shipments/{id}", one, K.NOT_RAKAM))
