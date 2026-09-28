"""Sorgu bilgisi kabulü — Grup 4: M19 içerik ve tasarım, M53 set / hediye / promosyon, M24 katalog ve bülten.

K1–K3 (`kabul.py`) her uçta; doğrudan SQL referansları:
  P4  içerik özeti: «Yeni talep» = son 24 saat sayım sorgusunun sonucu;
  P5  kataloglar: ekrandaki katalog sayısı = katalog listesinin portal sorgusunun satır sayısı.
Yalnız GET; Logo / CRM / T-soft'a yazmaz. `kabul.py` bu modülü `run(h, heavy)` ile çağırır.
"""
from __future__ import annotations

from urllib.parse import quote


def _ep(h, heavy: bool, name: str, path: str, ignore=()):
    st, out = h.http(path)
    h.check(f"{name} · HTTP 200", st == 200, str(st))
    if st != 200:
        return None, {}, {}
    k = h.contract(name, out, ignore)
    return out, k, h.run_all(name, k, heavy)


def _first(out, key: str = "items") -> str:
    return (((out or {}).get(key) or [{}])[0] or {}).get("id") or ""


def run(h, heavy: bool) -> None:
    from semantic_bridge import catalogs_kaynak as KCAT
    from semantic_bridge import marketing_creative_kaynak as KC
    from semantic_bridge import sets_kaynak as KS

    out, _k, got = _ep(h, heavy, "M19 özet", "/api/v1/marketing/creative/summary", KC.NOT_RAKAM)
    if out is not None and got.get("icerik.ozet.yeni"):
        v = h.num(next(iter(got["icerik.ozet.yeni"][0].values())))
        h.check("M19 özet · P4 yeni talep = sayım sorgusu", h.num(out.get("yeniTalep")) == v or None, f"{out.get('yeniTalep')} / {v}")
    req, _k, _g = _ep(h, heavy, "M19 talepler", "/api/v1/marketing/creative/requests", KC.NOT_RAKAM)
    _ep(h, heavy, "M19 bekleyen materyal", "/api/v1/marketing/creative/materials/pending", KC.NOT_RAKAM)
    _ep(h, heavy, "M19 arşiv", "/api/v1/marketing/creative/assets", KC.NOT_RAKAM)
    if _first(req):
        _ep(h, heavy, "M19 talep", f"/api/v1/marketing/creative/requests/{quote(_first(req))}", KC.NOT_RAKAM)

    sets, _k, _g = _ep(h, heavy, "M53 setler", "/api/v1/marketing/sets", KS.NOT_RAKAM)
    for sub in ("meta", "status", "books", "basket-pairs", "suggestions"):
        _ep(h, heavy, f"M53 {sub}", f"/api/v1/marketing/sets/{sub}", KS.NOT_RAKAM)
    if _first(sets):
        _ep(h, heavy, "M53 set kartı", f"/api/v1/marketing/sets/{quote(_first(sets))}", KS.NOT_RAKAM)
        _ep(h, heavy, "M53 set etkisi", f"/api/v1/marketing/sets/{quote(_first(sets))}/effect", KS.NOT_RAKAM)
    offers, _k, _g = _ep(h, heavy, "M53 hediye teklifleri", "/api/v1/marketing/gift-offers", KS.NOT_RAKAM)
    if _first(offers):
        _ep(h, heavy, "M53 hediye teklifi", f"/api/v1/marketing/gift-offers/{quote(_first(offers))}", KS.NOT_RAKAM)
    _ep(h, heavy, "M53 promosyon ürünleri", "/api/v1/marketing/promo-items", KS.NOT_RAKAM)

    _ep(h, heavy, "M24 meta", "/api/v1/catalog-newsletter/meta", KCAT.NOT_RAKAM)
    cats, _k, got = _ep(h, heavy, "M24 kataloglar", "/api/v1/catalog-newsletter/catalogs", KCAT.NOT_RAKAM)
    if cats is not None and "katalog.liste" in got:
        n = len(cats.get("items") or [])
        h.check("M24 kataloglar · P5 katalog sayısı = liste sorgusu satırı", n == len(got["katalog.liste"]),
                f"{n} / {len(got['katalog.liste'])}")
    if _first(cats):
        _ep(h, heavy, "M24 katalog", f"/api/v1/catalog-newsletter/catalogs/{quote(_first(cats))}", KCAT.NOT_RAKAM)
    nls, _k, _g = _ep(h, heavy, "M24 bültenler", "/api/v1/catalog-newsletter/newsletters", KCAT.NOT_RAKAM)
    if _first(nls):
        _ep(h, heavy, "M24 bülten", f"/api/v1/catalog-newsletter/newsletters/{quote(_first(nls))}", KCAT.NOT_RAKAM)
    _ep(h, heavy, "M24 rapor", "/api/v1/catalog-newsletter/report", KCAT.NOT_RAKAM)
