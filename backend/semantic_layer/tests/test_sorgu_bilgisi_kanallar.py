"""Sorgu bilgisi — M42 Kanallar ve D2C (G5 yayılımı): karne, kanal detayı, kitaplar, iadeler, matris, hedef, simülasyon,
D2C, eşleme ve panel dosyası uçlarında kaynaksız rakam yok; kanal tablosunu dolduran Logo sorgusu yıl anahtarıyla köken.
Kabul: `scripts/acceptance/sorgu-bilgisi/g5_kanallar.py`.
"""
from __future__ import annotations

import json

from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import d2c as D
from semantic_bridge.channels import imports as I
from semantic_bridge.channels import kaynak as K
from semantic_bridge.channels import refresh as RF
from semantic_bridge.channels import scorecard as SC
from semantic_bridge.channels import store as S
from semantic_layer.tests.test_channels import T, _seed, _st
from semantic_layer.tests.test_channels import engine  # noqa: F401 — fixture


def _check(out: dict) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    assert k["sources"]
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [], s
        assert s["connection"] in ("logo", "crm", "portal")
    json.dumps(out, default=str)
    return k


def _with(engine, build, fn, *a, **kw):
    with Y.yakala(engine) as q:
        out = fn(*a, **kw)
    return P.ekle(out, build(engine, T, out, q))


def test_scorecard_with_year_origin(engine):
    _seed(engine)
    y = Y.Yakalanan()
    y.ekle("logo", "SELECT C.CODE AS grup, MONTH(S.DATE_) AS ay FROM dbo.LG_411_01_STLINE AS S JOIN dbo.LG_411_CLCARD AS C "
                   "ON C.LOGICALREF = S.CLIENTREF WHERE S.DATE_ >= '20260101'", 48, 900, "TIGERDB")
    assert Y.koken_yaz(engine, T, RF.koken_yil(2026), y) == 1
    k = _check(_with(engine, K.for_scorecard, SC.scorecard, engine, T, 2026, 7))
    cari = [s for s in k["sources"].values() if "semantic_channel_cari_months" in s["sql"]]
    assert cari and any(k["sources"][o]["connection"] == "logo" for s in cari for o in s["origin"])


def test_channel_books_returns_matrix_targets_simulation(engine):
    _seed(engine)
    _check(_with(engine, K.for_channel, SC.channel, engine, T, "hepsiburada", 2026, 7))
    _check(_with(engine, K.for_books, SC.books, engine, T, "hepsiburada", 2026, 7))
    _check(_with(engine, K.for_returns, SC.returns, engine, T, "kitapyurdu", 2026, 2, 3))
    _check(_with(engine, K.for_matrix, SC.matrix, engine, T, 2026, 7))
    _check(_with(engine, K.for_targets, SC.targets, engine, T, 2026))
    _check(_with(engine, K.for_simulate, SC.simulate, engine, T, {"platform": "kitapyurdu", "yil": 2026, "ay": 7, "iskontoPuan": 2}))


def test_d2c_accounts_suggestions(engine):
    _seed(engine)
    _check(_with(engine, K.for_d2c, D.overview, engine, T, _st(d2cMinAdet=20, d2cIndex=1.5), 2026, 7))
    with Y.yakala(engine) as q:
        items = S.accounts(engine, T)
        cards = S.meta_get(engine, T, "cards")
    out = {"items": items, "counts": {"onayli": len(items)}, "cards": cards, "specodes": ["E-TICARET"]}
    _check(P.ekle(out, K.for_accounts(engine, T, out, q)))
    D.suggest_set(engine, T, "ayse", _st(d2cMinAdet=20, d2cIndex=1.5), [], None, 2026, 7)
    with Y.yakala(engine) as q:
        out = {"items": S.suggestions(engine, T)}
    _check(P.ekle(out, K.for_suggestions(engine, T, out, q)))


def test_import_sell_through(engine):
    _seed(engine)
    S.replace_all(engine, T, S.BARCODES, [{"barkod": "9786050000001", "stok_kodu": "B1"}])
    csv_text = "Barkod;Ürün Adı;Satış Adedi;Stok\n9786050000001;Birinci Kitap;5;12\n"
    head = I.store_import(engine, T, "ayse", "hepsiburada", "rapor.csv", csv_text.encode("utf-8"), "2026-07-01", "2026-07-31")
    with Y.yakala(engine) as q:
        months = SC.months_between("2026-07-01", "2026-07-31")
        out = I.sell_through(engine, T, head["id"], SC.sell_in_books(engine, T, "hepsiburada", months))
    out["kanalaSatisAylari"] = [f"{y}-{m:02d}" for y, m in months]
    _check(P.ekle(out, K.for_import(engine, T, out, q)))
    with Y.yakala(engine) as q:
        out = {"items": I.list_imports(engine, T)}
    _check(P.ekle(out, K.for_imports(engine, T, out, q)))
