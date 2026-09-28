"""Sorgu bilgisi kabulü — Grup 4: M16 lansman, M17 backlist.

K1–K3 (`kabul.py`) her uçta; doğrudan SQL referansları:
  P2  lansman listesi: ekrandaki lansman sayısı = lansman listesinin portal sorgusunun satır sayısı;
  P3  backlist: kitap panelinin gün / seri satırı sayısı = kitabın aylık seri sorgusunun satır sayısı.
Yalnız GET; Logo / CRM'e yazmaz. `kabul.py` bu modülü `run(h, heavy)` ile çağırır.
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


def run(h, heavy: bool) -> None:
    from semantic_bridge.marketing import kaynak_backlist as KB
    from semantic_bridge.marketing import kaynak_lansman as KL

    out, _k, got = _ep(h, heavy, "M16 lansmanlar", "/api/v1/marketing/launches", KL.NOT_RAKAM)
    if out is not None and "lansman.liste" in got:
        n = len(out.get("items") or [])
        h.check("M16 lansmanlar · P2 lansman sayısı = liste sorgusu satırı", n == len(got["lansman.liste"]),
                f"{n} / {len(got['lansman.liste'])}")
    _ep(h, heavy, "M16 bugün", "/api/v1/marketing/launches/today", KL.NOT_RAKAM)
    lid = ((out or {}).get("items") or [{}])[0].get("id")
    if lid:
        for sub, name in (("", "kart"), ("/tracking", "izleme"), ("/events", "etkinlikler"), ("/media", "medya"),
                          ("/reviews", "değerlendirme")):
            _ep(h, heavy, f"M16 lansman {name}", f"/api/v1/marketing/launches/{quote(lid)}{sub}", KL.NOT_RAKAM)
    else:
        h.check("M16 lansman kartı", None, "lansman yok; kart uçları atlandı")

    bl, _k, _g = _ep(h, heavy, "M17 backlist", "/api/v1/marketing/backlist", KB.NOT_RAKAM)
    _ep(h, heavy, "M17 ajanda", "/api/v1/marketing/backlist/agenda", KB.NOT_RAKAM)
    _ep(h, heavy, "M17 kampanya etkileri", "/api/v1/marketing/backlist/effects", KB.NOT_RAKAM)
    _ep(h, heavy, "M17 aktivasyon planları", "/api/v1/marketing/backlist/activations", KB.NOT_RAKAM)
    code = ((bl or {}).get("items") or [{}])[0].get("stokKodu")
    if code:
        det, _k, got = _ep(h, heavy, "M17 kitap paneli", f"/api/v1/marketing/backlist/{quote(code)}", KB.NOT_RAKAM)
        if det is not None and "backlist.seri" in got:
            seri = det.get("seri") or det.get("aylik") or []
            h.check("M17 kitap paneli · P3 seri satırı = seri sorgusu satırı", len(seri) == len(got["backlist.seri"]) or None,
                    f"{len(seri)} / {len(got['backlist.seri'])}")
    else:
        h.check("M17 kitap paneli", None, "backlist satırı yok; panel atlandı")
