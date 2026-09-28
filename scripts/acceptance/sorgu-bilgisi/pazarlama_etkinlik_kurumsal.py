"""Sorgu bilgisi kabulü — Grup 4: M27 fuar ve etkinlik, M28 kurumsal ilişkiler.

K1–K3 (`kabul.py`) her uçta; doğrudan SQL referansları:
  P12 fuar kartları: ekrandaki kart sayısı = kart sorgusunun satır sayısı;
  P13 kurumsal ilişkiler: kişi kartı toplamı = etkin kişi sorgusunun satır sayısı;
  P14 fuar sonucu (varsa): «Net satış» = sonucun Logo fuar satışı sorgularının Σ ciro'su (kayıtlı sonuçsa UYARI).
KİŞİSEL VERİ: kişi kartı ad / iletişimi yazdırılmaz. Yalnız GET; CRM / Logo'ya yazmaz.
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
    from semantic_bridge import events_kaynak as EK
    from semantic_bridge import public_affairs_kaynak as PAK

    _ep(h, heavy, "M27 takvim", "/api/v1/events/calendar", EK.NOT_RAKAM)
    _ep(h, heavy, "M27 yaklaşanlar", "/api/v1/events/upcoming", EK.NOT_RAKAM)
    _ep(h, heavy, "M27 CRM etkinlikleri", "/api/v1/events/crm-events", EK.NOT_RAKAM)
    _ep(h, heavy, "M27 tip eşlemesi", "/api/v1/events/type-map", EK.NOT_RAKAM)
    fairs, _k, got = _ep(h, heavy, "M27 kartlar", "/api/v1/events/fairs", EK.NOT_RAKAM)
    if fairs is not None and "etk.kart" in got:
        n = len(fairs.get("items") or [])
        h.check("M27 kartlar · P12 kart sayısı = kart sorgusu", n == len(got["etk.kart"]), f"{n} / {len(got['etk.kart'])}")
    fid = ((fairs or {}).get("items") or [{}])[0].get("id")
    if fid:
        _ep(h, heavy, "M27 kart", f"/api/v1/events/fairs/{quote(fid)}", EK.NOT_RAKAM)
        res, _k, got = _ep(h, heavy, "M27 sonuç", f"/api/v1/events/fairs/{quote(fid)}/result", EK.NOT_RAKAM)
        r = (res or {}).get("result") or {}
        rows = [x for sid, v in got.items() if sid.startswith("etk.logo.sonuc.") for x in v]
        if r and rows:
            logo = round(sum(h.num(x.get("ciro")) for x in rows), 2)
            h.check("M27 sonuç · P14 net satış = Logo fuar satışı Σ ciro",
                    abs(h.num(r.get("netCiro")) - logo) < 0.01 or (None if r.get("cached") else False),
                    f"{r.get('netCiro')} / {logo}")
    _ep(h, heavy, "M27 ödüller", "/api/v1/events/awards", EK.NOT_RAKAM)

    _ep(h, heavy, "M28 ana ekran", "/api/v1/public-affairs/home", PAK.NOT_RAKAM)
    ppl, _k, got = _ep(h, heavy, "M28 kişiler", "/api/v1/public-affairs/people", PAK.NOT_RAKAM)
    if ppl is not None and "ki.kisi" in got:
        n = (ppl.get("counts") or {}).get("toplam")
        h.check("M28 kişiler · P13 kişi kartı toplamı = kişi sorgusu", n == len(got["ki.kisi"]), f"{n} / {len(got['ki.kisi'])}")
    pid = ((ppl or {}).get("items") or [{}])[0].get("id")
    if pid:
        _ep(h, heavy, "M28 kişi kartı", f"/api/v1/public-affairs/people/{quote(pid)}", PAK.NOT_RAKAM)
    orgs, _k, _g = _ep(h, heavy, "M28 kurumlar", "/api/v1/public-affairs/orgs", PAK.NOT_RAKAM)
    oid = ((orgs or {}).get("items") or [{}])[0].get("id")
    if oid:
        _ep(h, heavy, "M28 kurum kartı", f"/api/v1/public-affairs/orgs/{quote(oid)}", PAK.NOT_RAKAM)
    _ep(h, heavy, "M28 hediye programı", "/api/v1/public-affairs/gifts", PAK.NOT_RAKAM)
    prj, _k, _g = _ep(h, heavy, "M28 projeler", "/api/v1/public-affairs/projects", PAK.NOT_RAKAM)
    jid = ((prj or {}).get("items") or [{}])[0].get("id")
    if jid:
        _ep(h, heavy, "M28 proje", f"/api/v1/public-affairs/projects/{quote(jid)}", PAK.NOT_RAKAM)
        _ep(h, heavy, "M28 proje erişimi", f"/api/v1/public-affairs/projects/{quote(jid)}/report", PAK.NOT_RAKAM)
    _ep(h, heavy, "M28 CRM rolleri", "/api/v1/public-affairs/crm/roles", PAK.NOT_RAKAM)
    _ep(h, heavy, "M28 rapor", "/api/v1/public-affairs/report", PAK.NOT_RAKAM)
