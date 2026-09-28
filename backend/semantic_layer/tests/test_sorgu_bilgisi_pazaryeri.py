"""Sorgu bilgisi — M40 Trendyol ve M41 Amazon/yurtdışı (G5 yayılımı): özet ve liste uçlarında kaynaksız rakam yok; panel
dosyası rakamı dosya satırlarının portal okumasına, Amazon rakamı gece okumasının Logo/CRM sorgusuna (köken) bağlı.
Kabul: `scripts/acceptance/sorgu-bilgisi/g5_pazaryeri.py`.
"""
from __future__ import annotations

import json

from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import amazon as A
from semantic_bridge.channels import kaynak_pazaryeri as KP
from semantic_bridge.channels import trendyol as T
from semantic_bridge.channels import trendyol_import as TI
from semantic_layer.tests import test_amazon as TA
from semantic_layer.tests.test_trendyol import CLAIMS_CSV, NOW, ORDERS_CSV, PRODUCTS_CSV, QUESTIONS_CSV, TN, _seed_logo, _st
from semantic_layer.tests.test_trendyol import engine  # noqa: F401 — fixture


def _check(out: dict) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, KP.NOT_RAKAM) == []
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
    return P.ekle(out, build(engine, TN, out, q))


def _seed(engine):
    _seed_logo(engine)
    for tur, name, data in (("urun", "urunler.csv", PRODUCTS_CSV), ("siparis", "siparis.csv", ORDERS_CSV),
                            ("iade", "iade.csv", CLAIMS_CSV), ("soru", "soru.csv", QUESTIONS_CSV)):
        TI.store(engine, TN, "ayse", tur, name, data)


def test_trendyol_overview_and_lists(engine):
    _seed(engine)
    st = _st()
    wholesale = {"eslendi": False, "neden": "Logo'da Trendyol'a bağlanmış cari yok."}
    k = _check(_with(engine, KP.ty_overview, T.overview, engine, TN, st, wholesale, NOW))
    assert any("semantic_trendyol_products" in s["sql"] for s in k["sources"].values())
    _check(_with(engine, KP.ty_list("urun"), T.products, engine, TN, st))
    _check(_with(engine, KP.ty_list("stok"), T.stock_diff, engine, TN, st))
    _check(_with(engine, KP.ty_list("fiyat"), T.price_diff, engine, TN, st))
    _check(_with(engine, KP.ty_list("siparis"), T.orders, engine, TN, now=NOW))
    _check(_with(engine, KP.ty_list("iade"), T.claims, engine, TN))
    _check(_with(engine, KP.ty_list("soru"), T.questions, engine, TN, st, now=NOW))
    _check(_with(engine, KP.ty_list("yorum"), T.reviews, engine, TN))
    _check(_with(engine, KP.ty_list("vitrin"), T.showcase, engine, TN, st))
    _check(_with(engine, KP.ty_list("hafta"), T.weekly, engine, TN, st, now=NOW))
    with Y.yakala(engine) as q:
        out = {"items": TI.list_imports(engine, TN), "types": T.TYPE_LABELS}
    _check(P.ekle(out, KP.ty_list("dosya")(engine, TN, out, q)))


def test_trendyol_logo_origin(engine):
    _seed(engine)
    y = Y.Yakalanan()
    y.ekle("logo", "SELECT I.CODE AS stok, 1 AS bakiye FROM dbo.LG_411_01_STLINE AS L JOIN dbo.LG_411_ITEMS AS I ON 1 = 1", 4, 30, "TIGERDB")
    Y.koken_yaz(engine, TN, T.KOKEN_LOGO, y)
    k = _check(_with(engine, KP.ty_list("stok"), T.stock_diff, engine, TN, _st()))
    logo_tbl = [s for s in k["sources"].values() if "semantic_trendyol_logo" in s["sql"]]
    assert logo_tbl and any(k["sources"][o]["connection"] == "logo" for s in logo_tbl for o in s["origin"])


def test_amazon_views_with_night_read_origin(engine, monkeypatch):
    A._ready.discard(id(engine))
    A.ensure(engine)
    TA._read(engine, monkeypatch)                 # gece okuması (sahte Logo/CRM): köken kaydı yazılır
    k = _check(_with(engine, KP.am_list("konsinye"), A.consignment, engine, TN, billed={"K1": 50.0}))
    cons = [s for s in k["sources"].values() if "semantic_intl_consignment" in s["sql"]]
    assert cons and cons[0]["origin"] and all(k["sources"][o]["connection"] in ("logo", "crm") for o in cons[0]["origin"])
    _check(_with(engine, KP.am_list("yurtdisi"), A.international, engine, TN))
    _check(_with(engine, KP.am_list("yurtdisiKitap"), A.intl_books, engine, TN))
    _check(_with(engine, KP.am_list("hak"), A.rights, engine, TN))
    wholesale = {"eslendi": False, "neden": "yok"}
    _check(_with(engine, KP.am_overview, A.overview, engine, TN, wholesale))
    with Y.yakala(engine) as q:
        out = {"items": A.params(engine, TN)}
    P.ekle(out, KP.am_list("param")(engine, TN, out, q))
    assert P.problems(out) == []
