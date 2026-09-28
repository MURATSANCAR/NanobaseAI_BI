"""Sorgu bilgisi kabulü — Grup 4: H2 okur veri tabanı, M37 okur topluluğu, okur sesi ve not sinyali panelleri.

K1–K3 (`kabul.py`) her uçta; doğrudan SQL referansları:
  P6  okur topluluğu segmentleri: ekrandaki segment sayısı = segment sorgusunun satır sayısı;
  P7  okur veri tabanı: «Tekil okur» = etkin okur profili sorgusunun satır sayısı (birleşen okur düşülmüşse fark UYARI).
KİŞİSEL VERİ: kabul yalnız sayıları karşılaştırır; okur satırı yazdırılmaz. Not sinyali için ortamda `KABUL_CARI`
(bir Logo cari kodu) verilirse o carinin kartı denetlenir. Yalnız GET; CRM'e yazmaz.
"""
from __future__ import annotations

import os
from urllib.parse import quote


def _ep(h, heavy: bool, name: str, path: str, ignore=()):
    st, out = h.http(path)
    h.check(f"{name} · HTTP 200", st == 200, str(st))
    if st != 200:
        return None, {}, {}
    k = h.contract(name, out, ignore)
    return out, k, h.run_all(name, k, heavy)


def run(h, heavy: bool) -> None:
    from semantic_bridge import okur_kaynak as OK
    from semantic_bridge import readers_kaynak as KR
    from semantic_bridge import signals_kaynak as SK

    ov, _k, got = _ep(h, heavy, "H2 özet", "/api/v1/readers/overview", KR.NOT_RAKAM)
    if ov is not None and "okur.profil" in got:
        n = h.num(ov.get("readers"))
        h.check("H2 özet · P7 tekil okur = etkin profil sorgusu", n == len(got["okur.profil"]) or None,
                f"{int(n)} / {len(got['okur.profil'])}")
    for sub in ("sources", "mine", "status", "merge-candidates?status=bekliyor", "segments", "imports", "exports"):
        _ep(h, heavy, f"H2 {sub.split('?')[0]}", f"/api/v1/readers/{sub}", KR.NOT_RAKAM)

    _ep(h, heavy, "M37 özet", "/api/v1/okur/overview", OK.NOT_RAKAM)
    _ep(h, heavy, "M37 izin sağlığı", "/api/v1/okur/consent-health", OK.NOT_RAKAM)
    _ep(h, heavy, "M37 eğilim", "/api/v1/okur/inventory", OK.NOT_RAKAM)
    _ep(h, heavy, "M37 ilgi alanları", "/api/v1/okur/categories", OK.NOT_RAKAM)
    segs, _k, got = _ep(h, heavy, "M37 segmentler", "/api/v1/okur/segments", OK.NOT_RAKAM)
    if segs is not None and "topluluk.segment" in got:
        h.check("M37 segmentler · P6 segment sayısı = segment sorgusu", segs.get("total") == len(got["topluluk.segment"]),
                f"{segs.get('total')} / {len(got['topluluk.segment'])}")
    sid = ((segs or {}).get("items") or [{}])[0].get("id")
    if sid:
        _ep(h, heavy, "M37 segment", f"/api/v1/okur/segments/{quote(sid)}", OK.NOT_RAKAM)
    progs, _k, _g = _ep(h, heavy, "M37 programlar", "/api/v1/okur/programs", OK.NOT_RAKAM)
    pid = ((progs or {}).get("items") or [{}])[0].get("id")
    if pid:
        _ep(h, heavy, "M37 program", f"/api/v1/okur/programs/{quote(pid)}", OK.NOT_RAKAM)
    _ep(h, heavy, "M37 geçmiş etkinlikler", "/api/v1/okur/events-summary", OK.NOT_RAKAM)
    _ep(h, heavy, "M37 yorumlar", "/api/v1/okur/reviews", OK.NOT_RAKAM)

    _ep(h, heavy, "Okur sesi özeti", "/api/v1/okur-sesi/summary", SK.NOT_RAKAM)
    _ep(h, heavy, "Okur sesi etiketleri", "/api/v1/okur-sesi/labels?kaynak=site-yorum", SK.NOT_RAKAM)
    cari = os.environ.get("KABUL_CARI", "").strip()
    if cari:
        _ep(h, heavy, "Not sinyali", f"/api/v1/not-sinyali/cari/{quote(cari)}?ekran=musteri", SK.NOT_RAKAM)
    else:
        h.check("Not sinyali", None, "KABUL_CARI verilmedi; kart atlandı")
