"""H3 e-ticaret müşteri özeti hızı (2026-09-29): `GET /commerce/overview` 4,2 sn.

Neden: «en çok satanlar» ilk 10 satır için dönemin BÜTÜN barkodlarının adı aranıyordu — her istekte kitap dizininin tamamı
(tablo yansıtmasıyla) ve dizinde olmayan tek barkod bile varsa sitedeki bütün ürün kayıtları JSON gövdeleriyle okunup
çözülüyordu; dönem istatistiği her pencerede müşteri anahtarlarını 500'lük parçalarla ayrı sorgularda arıyordu.
Şimdi ad yalnız dönen satırlar için, haritalar uç belleğinde; ilk sipariş tek sorguda.

Eski hesap = yeni hesap: eski kodun birebir kopyası (`_old_*`) ile yeni `overview` her dönem için karşılaştırılır.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

import pytest
import sqlalchemy as sa

from semantic_bridge import categories as H1
from semantic_bridge import commerce as C
from semantic_bridge import commerce_sources as src
from semantic_bridge.seo_geo import store as SEO
from semantic_layer.tests.test_commerce import KEY, T, TODAY, FakeTsoft, conf, member, order
from semantic_layer.tests.test_commerce import _env, engine  # noqa: F401 — fixture

IN_INDEX = "9786050000011"
SITE_ONLY = "9786050000028"
NOWHERE = "9786050000035"
MANY = [f"97860500001{i:02d}" for i in range(12)]          # ilk 10'un dışına taşan barkodlar


def _seed(engine):
    orders = [
        order("O1", "2026-09-20 10:00:00", 100, member=11, email="a@x.com", lines=[(IN_INDEX, 2, 100)]),
        order("O2", "2026-09-21 10:00:00", 60, member=12, email="b@y.com", lines=[(SITE_ONLY, 5, 60)]),
        order("O3", "2026-09-22 10:00:00", 30, email="c@z.com", lines=[(NOWHERE, 1, 30)]),
        order("O4", "2026-09-27 10:00:00", 70, member=13, email="d@w.com", status="İptal edildi", lines=[(IN_INDEX, 9, 70)]),
        order("O5", "2026-08-25 10:00:00", 40, member=11, email="a@x.com", lines=[(SITE_ONLY, 1, 40)]),
        order("O6", "2026-09-26 10:00:00", 90, member=14, email="e@v.com",
              lines=[(b, {0: 6, 1: 7}.get(i, 1 + i % 3), 10 + i) for i, b in enumerate(MANY)]),
        order("O7", "2026-09-27 11:00:00", 15, email="f@u.com", lines=[(IN_INDEX, 1, 15)]),
    ]
    C.sync(engine, T, FakeTsoft(orders=orders, members=[member(11, "a@x.com"), member(12, "b@y.com"), member(13, "d@w.com"),
                                                        member(14, "e@v.com")]), conf(), full=True, today=TODAY, key=KEY)
    H1.PROFILES.create(engine, checkfirst=True)
    SEO.PRODUCTS.create(engine, checkfirst=True)
    now = datetime(2026, 9, 28, 3, 0)
    with engine.begin() as c:
        c.execute(H1.PROFILES.insert(), [
            {"tenant_id": T, "book_id": "b1", "ean": IN_INDEX, "name": "Dizindeki Kitap", "status": "yok", "fields_json": "{}",
             "crm_snapshot_json": "{}"},
            {"tenant_id": T, "book_id": "b2", "ean": MANY[0], "name": "", "status": "yok", "fields_json": "{}",
             "crm_snapshot_json": "{}"},
            {"tenant_id": T, "book_id": "b3", "ean": MANY[1], "name": "Çok Satan 1", "status": "yok", "fields_json": "{}",
             "crm_snapshot_json": "{}"}])
        c.execute(SEO.PRODUCTS.insert(), [
            {"tenant_id": T, "product_id": "p1", "code": "p1", "name": "", "active": True, "score": 0, "issues_json": "[]",
             "data_json": json.dumps({"Barcode": SITE_ONLY, "StatViews": 5}), "synced_at": now},
            {"tenant_id": T, "product_id": "p2", "code": "p2", "name": "Sitedeki Ad", "active": True, "score": 0, "issues_json": "[]",
             "data_json": json.dumps({"Barcode": SITE_ONLY}), "synced_at": now},
            {"tenant_id": T, "product_id": "p3", "code": "p3", "name": "İkinci Kopya", "active": True, "score": 0, "issues_json": "[]",
             "data_json": json.dumps({"Barcode": SITE_ONLY}), "synced_at": now},
            {"tenant_id": T, "product_id": "p4", "code": "p4", "name": "Sitede Çok Satan", "active": False, "score": 0,
             "issues_json": "[]", "data_json": json.dumps({"ProductBarcode": MANY[0]}), "synced_at": now}])


# ------------------------------------------------------------------ eski kodun kopyası (değiştirilmeden)


def _old_window_stats(engine, tenant, s, e):
    lo, hi = datetime.combine(s, datetime.min.time()), datetime.combine(e, datetime.min.time())
    O = C.ORDERS
    with engine.connect() as c:
        rows = list(c.execute(sa.select(O.c.valid, O.c.total, O.c.customer_key, O.c.is_guest)
                              .where(O.c.tenant_id == tenant, O.c.ordered_at >= lo, O.c.ordered_at < hi)))
        keys = sorted({r.customer_key for r in rows if r.valid and r.customer_key})
        firsts = {}
        for part in src.chunks(keys):
            for r in c.execute(sa.select(O.c.customer_key, sa.func.min(O.c.ordered_at).label("f"))
                               .where(O.c.tenant_id == tenant, O.c.valid.is_(True), O.c.customer_key.in_(part))
                               .group_by(O.c.customer_key)):
                firsts[r.customer_key] = r.f
    valid = [r for r in rows if r.valid]
    rev = sum(float(r.total or 0) for r in valid)
    new = sum(1 for k in keys if firsts.get(k) is not None and lo <= firsts[k] < hi)
    return {"siparis": len(valid), "ciro": round(rev, 2), "sepet": round(rev / len(valid), 2) if valid else None,
            "musteri": len(keys), "yeni": new, "tekrar": len(keys) - new, "iptal": len(rows) - len(valid),
            "misafir": sum(1 for r in valid if r.is_guest), "anahtarsiz": sum(1 for r in valid if not r.customer_key)}


def _old_book_names(engine, tenant, barcodes):
    idx = src.book_index(engine, tenant)["books"]
    out = {b: idx[b]["name"] for b in barcodes if b in idx and idx[b].get("name")}
    miss = [b for b in barcodes if b not in out]
    if miss:
        for p in src.site_products(engine, tenant):
            if p["barcode"] in miss and p["name"] and p["barcode"] not in out:
                out[p["barcode"]] = p["name"]
    return out


def _old_top_books(engine, tenant, s, e, n=10, names=None):
    lo, hi = datetime.combine(s, datetime.min.time()), datetime.combine(e, datetime.min.time())
    agg = defaultdict(lambda: [0.0, 0.0, 0])
    L, O = C.LINES, C.ORDERS
    with engine.connect() as c:
        for r in c.execute(sa.select(L.c.barcode, L.c.code, L.c.qty, L.c.amount)
                           .select_from(L.join(O, sa.and_(O.c.tenant_id == L.c.tenant_id, O.c.order_no == L.c.order_no)))
                           .where(L.c.tenant_id == tenant, O.c.valid.is_(True), O.c.ordered_at >= lo, O.c.ordered_at < hi)):
            k = r.barcode or r.code or "?"
            agg[k][0] += float(r.qty or 0)
            agg[k][1] += float(r.amount or 0)
            agg[k][2] += 1
    nm = _old_book_names(engine, tenant, list(agg))
    out = [{"barkod": k, "ad": nm.get(k), "adet": round(v[0], 2), "tutar": round(v[1], 2), "siparis": int(v[2])}
           for k, v in agg.items()]
    out.sort(key=lambda x: (-x["adet"], -x["tutar"], x["barkod"]))
    return out if n is None else out[:n]


def _old_overview(monkeypatch, engine, st, period):
    with monkeypatch.context() as m:
        m.setattr(C, "_window_stats", _old_window_stats)
        m.setattr(C, "top_books", _old_top_books)
        return C.overview(engine, T, st, period, today=TODAY)


# ------------------------------------------------------------------ testler


@pytest.mark.parametrize("period", ["dun", "hafta", "ay"])
def test_overview_equals_the_old_code(engine, monkeypatch, period):
    _seed(engine)
    st = C.settings(engine, T, conf())
    old = _old_overview(monkeypatch, engine, st, period)
    assert C.overview(engine, T, st, period, today=TODAY) == old
    maps = {"dizin": C.name_map_h1(engine, T), "site": C.name_map_site(engine, T)}
    cached = lambda bcs: C.book_names(engine, T, bcs, h1=lambda: maps["dizin"], site=lambda: maps["site"])  # noqa: E731
    assert C.overview(engine, T, st, period, today=TODAY, names=cached) == old


def test_names_and_top_list(engine):
    _seed(engine)
    top = C.top_books(engine, T, TODAY.replace(day=1), TODAY)
    by = {x["barkod"]: x["ad"] for x in top}
    assert len(top) == 10
    assert by[IN_INDEX] == "Dizindeki Kitap"            # iptal edilen O4 sayılmaz
    assert by[SITE_ONLY] == "Sitedeki Ad"               # adı boş ilk ürün atlanır, sonraki kopya değil ilk adlı ürün
    assert by[MANY[1]] == "Çok Satan 1"
    assert by.get(MANY[0]) == "Sitede Çok Satan"        # dizinde adı boş → sitedeki ad
    assert top == _old_top_books(engine, T, TODAY.replace(day=1), TODAY)
    everything = C.top_books(engine, T, TODAY.replace(day=1), TODAY, None)
    assert everything == _old_top_books(engine, T, TODAY.replace(day=1), TODAY, None) and len(everything) == 15
    assert NOWHERE not in by                            # 1 adet: ilk 10'un dışında


def test_names_are_looked_up_only_for_the_returned_rows_and_site_only_when_missing(engine):
    _seed(engine)
    asked: list[list[str]] = []
    site_reads = []

    def names(bcs):
        asked.append(list(bcs))
        return C.book_names(engine, T, bcs, h1=lambda: C.name_map_h1(engine, T),
                            site=lambda: site_reads.append(1) or C.name_map_site(engine, T))

    C.top_books(engine, T, TODAY.replace(day=1), TODAY, names=names)
    assert len(asked) == 1 and len(asked[0]) == 10
    site_reads.clear()
    assert C.book_names(engine, T, [IN_INDEX, MANY[1]], h1=lambda: C.name_map_h1(engine, T),
                        site=lambda: site_reads.append(1) or {}) == {IN_INDEX: "Dizindeki Kitap", MANY[1]: "Çok Satan 1"}
    assert site_reads == []                              # hepsi dizinde: site kayıtları okunmaz
    for bcs in ([IN_INDEX, SITE_ONLY, NOWHERE, MANY[0]], [], [NOWHERE], MANY):
        assert C.book_names(engine, T, bcs) == _old_book_names(engine, T, bcs)


def test_window_stats_single_query_equals_chunked(engine, monkeypatch):
    _seed(engine)
    monkeypatch.setattr(src, "chunks", lambda items, n=500: [items[i:i + 1] for i in range(len(items))])  # eski yol: tek tek
    for s, e in ((TODAY.replace(day=1), TODAY), (TODAY.replace(month=8, day=1), TODAY), (TODAY, TODAY)):
        assert C._window_stats(engine, T, s, e) == _old_window_stats(engine, T, s, e)
