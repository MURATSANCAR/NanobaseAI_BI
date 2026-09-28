"""Sorgu bilgisi kabulü — Grup 4 pazarlama çekirdeği: M15 yeni kitap planı ve karnesi, M18 aylık plan ve föy.

`kabul.py` ile aynı ölçüler (K1 kaynaksız rakam yok, K2 tutarlılık, K3 her SQL çalışır) ve doğrudan SQL referansı:
  P1  föy listesi: ekrandaki föy sayısı = föy listesinin portal sorgusunun satır sayısı.
Yalnız GET; Logo / CRM'e yazmaz. Kullanım: kabul.py bu modülü `run(h, heavy)` ile çağırır (h = kabul modülü).
"""
from __future__ import annotations

from datetime import date


def _ep(h, heavy: bool, name: str, path: str, ignore=()):
    st, out = h.http(path)
    h.check(f"{name} · HTTP 200", st == 200, str(st))
    if st != 200:
        return None, {}, {}
    k = h.contract(name, out, ignore)
    return out, k, h.run_all(name, k, heavy)


def run(h, heavy: bool) -> None:
    from semantic_bridge.marketing import kaynak_aylik as KA
    from semantic_bridge.marketing import kaynak_plan as KP

    ym = date.today().strftime("%Y-%m")
    _ep(h, heavy, "M15 yeni kitaplar", "/api/v1/marketing/new-books", KP.NOT_RAKAM)
    _ep(h, heavy, f"M18 ay {ym}", f"/api/v1/marketing/months/{ym}", KA.NOT_RAKAM)
    _ep(h, heavy, f"M18 çakışmalar {ym}", f"/api/v1/marketing/months/{ym}/conflicts", KA.NOT_RAKAM)
    _ep(h, heavy, f"M18 hedef açığı {ym}", f"/api/v1/marketing/months/{ym}/target-gaps", KA.NOT_RAKAM)
    _ep(h, heavy, f"M18 özel gün ve etkinlik {ym}", f"/api/v1/marketing/months/{ym}/events", KA.NOT_RAKAM)
    out, _k, got = _ep(h, heavy, f"M18 föyler {ym}", f"/api/v1/marketing/foy?donem={ym}", KA.NOT_RAKAM)
    if out is not None and "foy.liste" in got:
        n = len(out.get("items") or [])
        h.check(f"M18 föyler · P1 föy sayısı = föy sorgusu satırı", n == len(got["foy.liste"]), f"{n} / {len(got['foy.liste'])}")
