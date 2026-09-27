"""Çapraz yazar önerisi: sipariş eşitlemesi müşteri alanı saklamaz, ortak kitap çift üretmez, iptal/iade sayılmaz,
eşik (en az MIN_ORDERS ortak sipariş, lift ≥ MIN_LIFT) her yerde geçen kaydı eler, sonuç iki yönlü ve sayfalıdır."""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import author_copurchase as C
from semantic_layer.store.catalog_store import open_store

T = "t1"
X, Y, Z, ANON = ("aaaaaaaa-0000-0000-0000-00000000000" + c for c in "1234")


def _engine():
    e = open_store("sqlite://").engine
    C._ready.clear()
    C.ensure(e)
    return e


def _order(oid, day, barcodes, status="Teslim Edildi", deleted="0"):
    return {"OrderId": oid, "OrderDate": f"{day}T10:00:00+03:00", "OrderStatus": status, "OrderStatusId": "7", "IsDeleted": deleted,
            "CustomerName": "GİZLİ", "CustomerPhone": "555", "DeliveryAddress": {"City": "İst"},
            "OrderDetails": [{"OrderProductId": f"{oid}-{i}", "ProductId": str(i), "Barcode": b, "Quantity": "1"} for i, b in enumerate(barcodes)]}


def test_sync_keeps_no_customer_fields_and_pages():
    e = _engine()
    orders = [_order(str(i), "2026-09-0" + str(1 + i % 5), ["978-1"]) for i in range(7)]
    calls = []

    def call(path, params):
        calls.append(params)
        assert path == "order/get" and params["FetchProductData"] is True
        s, n = params["start"], params["limit"]
        return {"data": orders[s:s + n], "summary": {"totalRecordCount": len(orders)}}

    C.PAGE = 3
    try:
        out = C.sync(e, T, call, since=date(2026, 9, 1))
    finally:
        C.PAGE = 500
    assert out["read"] == 7 and out["lines"] == 7 and len(calls) == 3
    cols = {c.name for c in C.ORDERS.columns} | {c.name for c in C.LINES.columns}
    assert not any("customer" in c or "address" in c or "phone" in c for c in cols)
    with e.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(C.LINES)).scalar() == 7
        assert c.execute(sa.select(C.LINES.c.barcode)).first()[0] == "9781"
    # yeniden eşitleme aynı siparişi çoğaltmaz
    C.sync(e, T, lambda p, q: {"data": orders[q["start"]:q["start"] + q["limit"]]}, since=date(2026, 9, 1))
    with e.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(C.ORDERS)).scalar() == 7


def test_pairs_threshold_coauthor_and_cancelled():
    e = _engine()
    authors = {"1": {X}, "2": {Y}, "3": {Z}, "4": {X, Y}, "9": {ANON}}
    titles = {"1": "Kitap X", "2": "Kitap Y", "3": "Kitap Z", "4": "Ortak", "9": "Derleme"}
    names = {X: "Yazar X", Y: "Yazar Y", Z: "Yazar Z", ANON: "Anonim"}
    orders = []
    for i in range(4):
        orders.append(_order(f"xy{i}", "2026-09-01", ["1", "2"]))           # X + Y birlikte: 4 sipariş
    orders.append(_order("co", "2026-09-01", ["4"]))                       # yalnız ortak kitap: çift sayılmaz
    orders.append(_order("xz", "2026-09-01", ["1", "3"]))                  # X + Z tek sipariş: eşik altı
    for i in range(3):
        orders.append(_order(f"iptal{i}", "2026-09-01", ["2", "3"], status="İptal Edildi"))
    for i in range(30):
        orders.append(_order(f"an{i}", "2026-09-01", ["9", "3" if i % 2 else "1"]))  # Anonim her yerde: lift düşük
    for i in range(30):
        orders.append(_order(f"z{i}", "2026-09-02", ["3"]))
    for i in range(20):
        orders.append(_order(f"x{i}", "2026-09-03", ["1"]))                # X çok satan yazar: Anonim×X lift ~1,05
    C.sync(e, T, lambda p, q: {"data": orders[q["start"]:q["start"] + q["limit"]]}, since=date(2026, 9, 1))
    out = C.compute(e, T, authors, titles, names)
    assert out["orders_counted"] == len(orders) - 3
    rx = C.related(e, T, X)
    assert [r["contactId"] for r in rx["items"]] == [Y] and rx["items"][0]["orders"] == 4
    assert rx["items"][0]["books"][0] == {"a": "Kitap X", "b": "Kitap Y", "orders": 4}
    assert C.related(e, T, Y)["items"][0]["contactId"] == X            # iki yönlü
    assert all(r["contactId"] != ANON for r in C.related(e, T, Z)["items"])
    assert C.related(e, T, ANON)["total"] == 0


def test_run_due_is_system_only():
    assert A.rule_for("/api/v1/editorial/authors/copurchase/run-due") == A.SYSTEM
    assert A.page("yazar-iliskileri") in A.rule_for("/api/v1/editorial/authors/related/x")


def test_turkish_status_names():
    assert not C.counted("İptal Edildi", False) and not C.counted("İADE", False) and not C.counted("Kısmi İade", False)
    assert C.counted("Teslim Edildi", False) and C.counted("Ödeme Bekleniyor", False) and not C.counted("Teslim Edildi", True)
