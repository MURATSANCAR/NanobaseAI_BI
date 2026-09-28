"""Sorgu bilgisi kabulü — Grup 4: M20 basın ilişkileri, M21 dijital reklam, M22 sosyal medya, M23 işbirlikleri.

K1–K3 (`kabul.py`) her uçta; doğrudan SQL referansları:
  P8  basın: PR dosyası sayısı = dosya listesi sorgusunun satır sayısı;
  P9  reklam: kampanya sayısı (süzgeçsiz) = kampanya sorgusunun satır sayısı;
  P10 sosyal medya: tanımlı hesap sayısı = hesap sorgusunun satır sayısı;
  P11 işbirlikleri: kayıt defterindeki kişi sayısı = kişi sorgusunun satır sayısı.
KİŞİSEL VERİ: medya kişisi ve içerik üreticisi adı / iletişimi yazdırılmaz; yalnız sayı karşılaştırılır. Yalnız GET.
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


def _count(h, name: str, shown, got: dict, sid: str) -> None:
    if sid in got:
        h.check(f"{name} = {sid} satırı", shown == len(got[sid]), f"{shown} / {len(got[sid])}")


def run(h, heavy: bool) -> None:
    from semantic_bridge import ads_kaynak as AK
    from semantic_bridge import influencers_kaynak as IK
    from semantic_bridge import pr_kaynak as PRK
    from semantic_bridge import social_kaynak as SOK

    _ep(h, heavy, "M20 bugün", "/api/v1/pr/home", PRK.NOT_RAKAM)
    kits, _k, got = _ep(h, heavy, "M20 dosyalar", "/api/v1/pr/kits", PRK.NOT_RAKAM)
    if kits is not None:
        _count(h, "M20 dosyalar · P8 dosya sayısı", kits.get("total"), got, "pr.dosya")
    kid = ((kits or {}).get("items") or [{}])[0].get("id")
    if kid:
        _ep(h, heavy, "M20 dosya", f"/api/v1/pr/kits/{quote(kid)}", PRK.NOT_RAKAM)
        _ep(h, heavy, "M20 öneri", f"/api/v1/pr/kits/{quote(kid)}/suggest-contacts", PRK.NOT_RAKAM)
    cts, _k, _g = _ep(h, heavy, "M20 kişiler", "/api/v1/pr/contacts", PRK.NOT_RAKAM)
    ckey = ((cts or {}).get("items") or [{}])[0].get("key")
    if ckey:
        _ep(h, heavy, "M20 kişi kartı", f"/api/v1/pr/contacts/{quote(ckey)}", PRK.NOT_RAKAM)
    _ep(h, heavy, "M20 yansımalar", "/api/v1/pr/coverage", PRK.NOT_RAKAM)
    _ep(h, heavy, "M20 rapor", "/api/v1/pr/report", PRK.NOT_RAKAM)

    _ep(h, heavy, "M21 özet", "/api/v1/ads/overview", AK.NOT_RAKAM)
    _ep(h, heavy, "M21 yenileme durumu", "/api/v1/ads/status", AK.NOT_RAKAM)
    _ep(h, heavy, "M21 hesaplar", "/api/v1/ads/accounts", AK.NOT_RAKAM)
    _ep(h, heavy, "M21 yüklemeler", "/api/v1/ads/imports", AK.NOT_RAKAM)
    camps, _k, got = _ep(h, heavy, "M21 kampanyalar", "/api/v1/ads/campaigns", AK.NOT_RAKAM)
    if camps is not None:
        _count(h, "M21 kampanyalar · P9 kampanya sayısı", camps.get("total"), got, "reklam.kampanya")
    _ep(h, heavy, "M21 bütçe", "/api/v1/ads/budget", AK.NOT_RAKAM)
    _ep(h, heavy, "M21 CRM kayıtları", "/api/v1/ads/crm", AK.NOT_RAKAM)
    _ep(h, heavy, "M21 öneriler", "/api/v1/ads/suggestions", AK.NOT_RAKAM)
    _ep(h, heavy, "M21 brief'ler", "/api/v1/ads/briefs", AK.NOT_RAKAM)

    accs, _k, got = _ep(h, heavy, "M22 hesaplar", "/api/v1/social/accounts", SOK.NOT_RAKAM)
    if accs is not None:
        _count(h, "M22 hesaplar · P10 hesap sayısı", accs.get("total"), got, "sosyal.hesap")
    _ep(h, heavy, "M22 takvim", "/api/v1/social/calendar", SOK.NOT_RAKAM)
    _ep(h, heavy, "M22 fırsatlar", "/api/v1/social/opportunities", SOK.NOT_RAKAM)
    posts, _k, _g = _ep(h, heavy, "M22 gönderiler", "/api/v1/social/posts", SOK.NOT_RAKAM)
    pid = ((posts or {}).get("items") or [{}])[0].get("id")
    if pid:
        _ep(h, heavy, "M22 gönderi", f"/api/v1/social/posts/{quote(pid)}", SOK.NOT_RAKAM)
    _ep(h, heavy, "M22 içe aktarmalar", "/api/v1/social/imports", SOK.NOT_RAKAM)
    _ep(h, heavy, "M22 rapor", "/api/v1/social/report", SOK.NOT_RAKAM)

    _ep(h, heavy, "M23 pano", "/api/v1/influencers/board", IK.NOT_RAKAM)
    ppl, _k, got = _ep(h, heavy, "M23 kişiler", "/api/v1/influencers/people", IK.NOT_RAKAM)
    if ppl is not None:
        _count(h, "M23 kişiler · P11 kişi sayısı", ppl.get("total"), got, "isb.kisi")
    pers = ((ppl or {}).get("items") or [{}])[0].get("id")
    if pers:
        _ep(h, heavy, "M23 kişi kartı", f"/api/v1/influencers/people/{quote(pers)}", IK.NOT_RAKAM)
    _ep(h, heavy, "M23 CRM özeti", "/api/v1/influencers/crm/summary", IK.NOT_RAKAM)
    _ep(h, heavy, "M23 ödemeler", "/api/v1/influencers/payouts", IK.NOT_RAKAM)
    _ep(h, heavy, "M23 rapor", "/api/v1/influencers/report", IK.NOT_RAKAM)
