"""M41/M42 platform kitap listesi hızı (2026-09-29): `GET /channels/amazon/books` 4,3 sn — yılın bütün e-ticaret
kitap satırları okunup Python'da platforma süzülüyordu. Artık yalnız platformun grupları ve dönemin ayları okunur.

Eski hesap = yeni hesap: eski kodun (bütün yılı okuyan `_book_rows`) birebir kopyasıyla kitap listesi, iade listesi,
dönem sell-in adedi ve M9 tamamlaması her platform, yıl, ay ve eşlenmemiş sütun için karşılaştırılır.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

import pytest
import sqlalchemy as sa

from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import scorecard as SC
from semantic_bridge.channels import store as S
from semantic_layer.tests.test_channels import T, _seed
from semantic_layer.tests.test_channels import engine  # noqa: F401 — fixture


# ------------------------------------------------------------------ eski kodun kopyası (değiştirilmeden)


def _old_rows(engine, tenant, yil):
    with engine.connect() as c:
        return c.execute(sa.select(S.BOOK_MONTHS).where(S.BOOK_MONTHS.c.tenant_id == tenant, S.BOOK_MONTHS.c.yil == yil)).all()


def _old_books(engine, tenant, platform, yil=None, ay=None, q="", sort="netCiro", page=0, size=SC.PAGE):
    SC._check_platform(platform)
    p = SC.period(engine, tenant, yil, ay)
    SC.need_read(engine, tenant, [p["yil"]])
    mp = SC.Mapping(engine, tenant)
    agg = SC._book_sum(_old_rows(engine, tenant, p["yil"]), SC._window(p, p["yil"]), lambda r: mp.platform(r.grup) == platform)
    names = S.book_names(engine, tenant, list(agg))
    rows = [SC._book_view(k, v, names.get(k, "")) for k, v in agg.items()]
    rows = SC._search(rows, q)
    key = sort if sort in ("netCiro", "netAdet", "iadeAdet", "iadeOrani", "satisAdet", "marj") else "netCiro"
    rows.sort(key=lambda r: (-(r[key] if r[key] is not None else -math.inf), r["stokKodu"]))
    return SC._page(rows, page, {"period": p, "platform": platform, "sort": key}, size)


def _old_returns(engine, tenant, platform, yil=None, ay=None, months=3, page=0, size=SC.PAGE):
    SC._check_platform(platform)
    p = SC.period(engine, tenant, yil, ay)
    months = max(1, min(24, int(months)))
    idx = p["yil"] * 12 + p["ay"] - 1
    span = [((i // 12), (i % 12) + 1) for i in range(idx - months + 1, idx + 1)]
    years = sorted({y for y, _ in span})
    SC.need_read(engine, tenant, years)
    mp = SC.Mapping(engine, tenant)
    agg = {}
    for yy in years:
        wts = {m: 1.0 for (y2, m) in span if y2 == yy}
        part = SC._book_sum(_old_rows(engine, tenant, yy), wts, lambda r: mp.platform(r.grup) == platform)
        for k, v in part.items():
            cur = agg.setdefault(k, {kk: 0.0 for kk in SC.BOOK_METRICS})
            for kk in SC.BOOK_METRICS:
                cur[kk] += v[kk]
    names = S.book_names(engine, tenant, list(agg))
    rows = [SC._book_view(k, v, names.get(k, "")) for k, v in agg.items() if v["iade_adet"] > 0]
    rows.sort(key=lambda r: (-r["iadeAdet"], r["stokKodu"]))
    first = span[0]
    return SC._page(rows, page, {"period": p, "platform": platform, "aralik": {"bas": f"{first[0]}-{first[1]:02d}",
                                                                              "bit": f"{p['yil']}-{p['ay']:02d}", "ay": months}}, size)


def _old_sell_in(engine, tenant, platform, months):
    mp = SC.Mapping(engine, tenant)
    out = defaultdict(float)
    for yy in sorted({y for y, _ in months}):
        wts = {m: 1.0 for (y2, m) in months if y2 == yy}
        for code, v in SC._book_sum(_old_rows(engine, tenant, yy), wts, lambda r: mp.platform(r.grup) == platform).items():
            out[code] += v["satis_adet"] - v["iade_adet"]
    return dict(out)


def _old_m9_books(engine, tenant, platform, p, mp):
    return SC._book_sum(_old_rows(engine, tenant, p["yil"]), SC._window(p, p["yil"]), lambda r: mp.platform(r.grup) == platform)


# ------------------------------------------------------------------ veri: Amazon carisi, Amazon'a eşlenen kanal kodu


def _seed_more(engine):
    _seed(engine)
    extra = []
    for y, months in ((2025, range(1, 13)), (2026, range(1, 9))):
        for m in months:
            extra += [
                {"yil": y, "ay": m, "grup": "AMZ1", "stok_kodu": "B1", "satis_adet": 7 * m, "iade_adet": m % 3, "satis_ciro": 70.5 * m,
                 "iade_ciro": 3.25 * (m % 3), "maliyet": 20, "maliyetli_ciro": 60, "maliyetsiz_adet": 1, "maliyetsiz_ciro": 10.5},
                {"yil": y, "ay": m, "grup": "AMZ1", "stok_kodu": "B4", "satis_adet": 3, "iade_adet": 1, "satis_ciro": 33.3,
                 "iade_ciro": 11.1, "maliyet": 0, "maliyetli_ciro": 0, "maliyetsiz_adet": 3, "maliyetsiz_ciro": 33.3},
                {"yil": y, "ay": m, "grup": "#K:AMAZONTR", "stok_kodu": "B2", "satis_adet": 2 * m, "iade_adet": 0, "satis_ciro": 21.0 * m,
                 "iade_ciro": 0, "maliyet": 5, "maliyetli_ciro": 15, "maliyetsiz_adet": 0, "maliyetsiz_ciro": 0},
                {"yil": y, "ay": m, "grup": "#K:BILINMEYEN", "stok_kodu": "B3", "satis_adet": 4, "iade_adet": 2, "satis_ciro": 40,
                 "iade_ciro": 20, "maliyet": 0, "maliyetli_ciro": 0, "maliyetsiz_adet": 4, "maliyetsiz_ciro": 40},
            ]
    with engine.begin() as c:
        c.execute(S.BOOK_MONTHS.insert(), [{**r, "tenant_id": T} for r in extra])
    S.upsert_books(engine, T, {"B4": "Dördüncü Kitap"})
    S.sync_accounts(engine, T, [{"cari_kodu": "AMZ1", "unvan": "AMAZON TURKEY PERAKENDE", "kanal": "E-TICARET", "ref": 9, "firma": "411"}], {})
    M.decide(engine, T, "ayse", "AMZ1", {"platform": "amazon"})
    M.set_kanal(engine, T, "ayse", "AMAZONTR", "amazon")


PLATFORMS = ["amazon", "hepsiburada", "kitapyurdu", "timas.com.tr", "trendyol", M.UNMAPPED]


def test_platform_groups_match_the_mapping(engine):
    _seed_more(engine)
    mp = SC.Mapping(engine, T)
    with engine.connect() as c:
        groups = {r[0] for r in c.execute(sa.select(S.BOOK_MONTHS.c.grup).where(S.BOOK_MONTHS.c.tenant_id == T))}
    for plat in PLATFORMS[:-1]:
        want = sorted(g for g in groups if mp.platform(g) == plat)
        have = SC._platform_groups(mp, plat)
        assert set(want) <= set(have), plat                 # okunan satırlar hesabın saydığı her grubu kapsar
        assert all(mp.platform(g) == plat for g in have), plat
    assert SC._platform_groups(mp, M.UNMAPPED) is None
    assert set(SC._platform_groups(mp, "amazon")) == {"AMZ1", "#K:AMAZONTR"}


@pytest.mark.parametrize("plat", PLATFORMS)
def test_books_returns_sell_in_and_m9_equal_the_old_code(engine, plat):
    _seed_more(engine)
    for yil, ay in ((2026, None), (2026, 3), (2025, None), (2025, 11), (None, None)):
        for sort in ("netCiro", "iadeAdet", "marj"):
            assert SC.books(engine, T, plat, yil, ay, sort=sort) == _old_books(engine, T, plat, yil, ay, sort=sort), (yil, ay, sort)
        assert SC.books(engine, T, plat, yil, ay, q="kitap", size=1, page=1) == _old_books(engine, T, plat, yil, ay, q="kitap", size=1, page=1)
        # 14 ay yalnız 2026'dan geriye (2024 okunmadı; eski kod da 409 verir).
        for months in (1, 3) + ((14,) if (yil or 2026) == 2026 else ()):
            assert SC.returns(engine, T, plat, yil, ay, months=months) == _old_returns(engine, T, plat, yil, ay, months=months)
        p = SC.period(engine, T, yil, ay)
        mp = SC.Mapping(engine, T)
        w = SC._window(p, p["yil"])
        new = SC._book_sum(SC._platform_book_rows(engine, T, p["yil"], mp, plat, w), w, lambda r: mp.platform(r.grup) == plat)
        assert new == _old_m9_books(engine, T, plat, p, mp)
    span = SC.months_between("2025-11-01", "2026-08-17")
    assert SC.sell_in_books(engine, T, plat, span) == _old_sell_in(engine, T, plat, span)


def test_amazon_list_reads_only_amazon_rows(engine):
    _seed_more(engine)
    seen: list[int] = []
    orig = SC._book_rows

    def spy(*a, **kw):
        rows = orig(*a, **kw)
        seen.append(len(rows))
        return rows

    SC._book_rows = spy
    try:
        out = SC.books(engine, T, "amazon", 2026, 3)
    finally:
        SC._book_rows = orig
    # Mart'a kadar 3 ay × (AMZ1: B1, B4 + #K:AMAZONTR: B2) = 9 satır; yılın bütün satırları (8 ay × 9) okunmaz.
    assert seen == [9]
    assert {x["stokKodu"]: x["netAdet"] for x in out["items"]} == {"B1": 7 * 6 - 3, "B4": 6.0, "B2": 12.0}
    assert out["items"][0]["ad"] == "Birinci Kitap"
    assert date.fromisoformat(out["period"]["veriSonu"]) == date(2026, 8, 17)
