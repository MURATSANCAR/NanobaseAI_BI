"""Google Merchant Center ürün durumu: ayrıştırma, durum sınıfı, sayfalama, T-soft eşlemesi, iş listesi kaynağı."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge.seo_geo import merchant as m
from semantic_bridge.seo_geo import worklist as w
from semantic_bridge.seo_geo.store import PRODUCTS

AT = datetime(2026, 9, 28, 12, tzinfo=timezone.utc)


def _product(offer, *, approved=("TR",), disapproved=(), pending=(), issues=(), gtins=("9786050812345",), title="Kitap"):
    return {
        "name": f"accounts/5411495322/products/tr~TR~{offer}",
        "offerId": offer,
        "contentLanguage": "tr",
        "feedLabel": "TR",
        "productAttributes": {"title": title, "gtins": list(gtins), "link": f"https://timas.com.tr/{offer}"},
        "productStatus": {
            "destinationStatuses": [
                {"reportingContext": "SHOPPING_ADS", "approvedCountries": list(approved),
                 "disapprovedCountries": list(disapproved), "pendingCountries": list(pending)},
            ],
            "itemLevelIssues": list(issues),
        },
    }


GTIN_BAD = {"code": "invalid_gtin", "severity": "DISAPPROVED", "resolution": "merchant_action", "attribute": "gtins",
            "reportingContext": "SHOPPING_ADS", "description": "Invalid GTIN", "detail": "Use a valid GTIN",
            "documentation": "https://support.google.com/merchants/answer/6239388", "applicableCountries": ["TR"]}
IMG_SMALL = {"code": "image_too_small", "severity": "DEMOTED", "resolution": "merchant_action",
             "attribute": "image_link", "reportingContext": "FREE_LISTINGS", "description": "Image too small"}
INFO = {"code": "missing_shipping_weight", "severity": "NOT_IMPACTED", "description": "Missing shipping weight"}


def test_parse_merges_contexts_and_takes_worst_severity():
    p = _product("1", approved=(), disapproved=("TR",),
                 issues=[GTIN_BAD, {**GTIN_BAD, "reportingContext": "FREE_LISTINGS", "severity": "DEMOTED"}, INFO])
    it = m.parse_product(p)
    assert it["offerId"] == "1" and it["title"] == "Kitap" and it["gtins"] == ["9786050812345"]
    assert it["status"] == m.DISAPPROVED and it["worst"] == "DISAPPROVED"
    assert [i["code"] for i in it["issues"]] == ["invalid_gtin", "missing_shipping_weight"]
    gtin = it["issues"][0]
    assert gtin["severity"] == "DISAPPROVED" and gtin["contexts"] == ["SHOPPING_ADS", "FREE_LISTINGS"]
    assert gtin["countries"] == ["TR"] and gtin["documentation"].startswith("https://support.google.com")


def test_classify():
    assert m.classify([{"approvedCountries": ["TR"]}], []) == m.APPROVED
    assert m.classify([{"approvedCountries": ["TR"]}], [INFO]) == m.APPROVED  # bilgi gösterimi etkilemez
    assert m.classify([{"approvedCountries": ["TR"]}], [IMG_SMALL]) == m.LIMITED
    assert m.classify([{"approvedCountries": ["TR"]}, {"disapprovedCountries": ["TR"]}], []) == m.LIMITED
    assert m.classify([{"disapprovedCountries": ["TR"]}], [GTIN_BAD]) == m.DISAPPROVED
    assert m.classify([{"pendingCountries": ["TR"]}], []) == m.PENDING
    assert m.classify([], []) == m.PENDING


def test_summary_counts():
    items = [m.parse_product(_product("1")),
             m.parse_product(_product("2", issues=[IMG_SMALL])),
             m.parse_product(_product("3", approved=(), disapproved=("TR",), issues=[GTIN_BAD])),
             m.parse_product(_product("4", approved=(), disapproved=("TR",), issues=[GTIN_BAD, IMG_SMALL])),
             m.parse_product(_product("5", approved=(), pending=("TR",)))]
    items[0]["productId"] = "p1"
    s = m.summarize(items)
    assert (s["total"], s["approved"], s["limited"], s["disapproved"], s["pending"]) == (5, 1, 1, 2, 1)
    assert (s["matched"], s["unmatched"]) == (1, 4)
    by = {i["code"]: i for i in s["issues"]}
    assert by["invalid_gtin"]["products"] == 2 and by["image_too_small"]["products"] == 2
    assert s["issues"][0]["code"] == "invalid_gtin"  # önce onaylamayan sorun
    assert by["invalid_gtin"]["attributeLabel"] == "barkod (GTIN)"


def test_fetch_follows_page_token_to_the_end():
    pages = {None: {"products": [{"offerId": str(i)} for i in range(1000)], "nextPageToken": "a/b"},
             "a/b": {"products": [{"offerId": str(i)} for i in range(1000, 2000)], "nextPageToken": "c"},
             "c": {"products": [{"offerId": "2000"}]}}
    urls = []

    def get(url):
        urls.append(url)
        tok = url.split("pageToken=")[1].replace("%2F", "/") if "pageToken=" in url else None
        return pages[tok]

    got = m.fetch("5411495322", get)
    assert len(got) == 2001
    assert urls[0] == "https://merchantapi.googleapis.com/products/v1/accounts/5411495322/products?pageSize=1000"
    assert "pageToken=a%2Fb" in urls[1] and len(urls) == 3


def test_fetch_stops_on_repeated_token():
    with pytest.raises(RuntimeError):
        m.fetch("1", lambda url: {"products": [], "nextPageToken": "same"})


def test_match_order():
    idx = m.match_index([("101", "TMS-1", "978-605-08-1234-5"), ("102", "tms-2", None), ("103", None, "9786050800001")])
    assert m.match("101", [], idx) == ("101", "kimlik")
    assert m.match("TMS-2", [], idx) == ("102", "kod")
    assert m.match("9786050812345", [], idx) == ("101", "barkod")
    assert m.match("online-xyz", ["9786050800001"], idx) == ("103", "gtin")
    assert m.match("yok", ["123"], idx) == (None, None)


def test_secrets_do_not_leak_into_messages():
    msg = m.safe("Google 401: token ya29.a0AfH6SMsecret-value rejected; Bearer abc.def "
                 "-----BEGIN PRIVATE KEY-----\nMIIEv\n-----END PRIVATE KEY-----")
    assert "ya29" not in msg and "abc.def" not in msg and "MIIEv" not in msg and "PRIVATE KEY" not in msg


def _db():
    eng = sa.create_engine("sqlite://")
    PRODUCTS.create(eng)
    with eng.begin() as c:
        for pid, code, bc, sales in (("p1", "K1", "9786050812345", 120), ("p2", "K2", "9786050800001", 5)):
            c.execute(PRODUCTS.insert().values(tenant_id="t", product_id=pid, code=code, name=pid, active=True, score=50,
                                               issues_json="[]", data_json=json.dumps({"Barcode": bc,
                                                                                       "CountTotalSales": sales}),
                                               synced_at=AT))
    return eng


def test_save_matches_and_writes_snapshot_and_history():
    eng = _db()
    raw = [_product("p1", approved=(), disapproved=("TR",), issues=[GTIN_BAD]),
           _product("K2", issues=[IMG_SMALL], gtins=()),
           _product("zzz", gtins=("0000000000000",))]
    data = m.save(eng, "t", "5411495322", raw, AT)
    s = data["summary"]
    assert (s["total"], s["disapproved"], s["limited"], s["approved"], s["unmatched"]) == (3, 1, 1, 1, 1)
    assert data["link"].endswith("a=5411495322")
    with eng.connect() as c:
        rows = {r.offer_id: r for r in c.execute(sa.select(m.ITEMS))}
        hist = c.execute(sa.select(m.HIST)).all()
    assert rows["p1"].product_id == "p1" and rows["p1"].match == "kimlik" and rows["p1"].issue_codes == ",invalid_gtin,"
    assert rows["K2"].product_id == "p2" and rows["K2"].match == "kod"
    assert rows["zzz"].product_id is None and rows["zzz"].issue_codes == ""
    assert len(hist) == 1 and m.connected(eng, "t")
    # İkinci okuma son durumu değiştirir, geçmişe ekler
    m.save(eng, "t", "5411495322", raw[:1], AT)
    with eng.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(m.ITEMS)).scalar() == 1
        assert c.execute(sa.select(sa.func.count()).select_from(m.HIST)).scalar() == 2


def test_save_error_keeps_old_data_and_hides_token():
    eng = _db()
    m.save(eng, "t", "1", [_product("p1")], AT)
    m.save_error(eng, "t", "Google 500: ya29.gizli", AT)
    with eng.connect() as c:
        r = c.execute(sa.select(m.SNAP)).first()
        assert c.execute(sa.select(sa.func.count()).select_from(m.ITEMS)).scalar() == 1
    assert "ya29" not in r.error and json.loads(r.data_json)["summary"]["total"] == 1


class _Env:
    def __init__(self, eng):
        self.eng, self.tenant = eng, "t"

    def has(self, table):
        return sa.inspect(self.eng).has_table(table.name)

    def products(self):
        return {"p1": {"sales": 120.0}, "p2": {"sales": 5.0}}

    def product_impressions(self, pid):
        return {"p1": 1000, "p2": 10}.get(pid, 0)


def test_worklist_source_one_item_per_code_skips_info():
    eng = _db()
    m.save(eng, "t", "1", [_product("p1", approved=(), disapproved=("TR",), issues=[GTIN_BAD, INFO]),
                           _product("K2", approved=(), disapproved=("TR",), issues=[GTIN_BAD, IMG_SMALL]),
                           _product("zzz", issues=[IMG_SMALL])], AT)
    items = {i["ref"]: i for i in w.src_merchant(_Env(eng))}
    assert set(items) == {"merchant:invalid_gtin", "merchant:image_too_small"}
    gtin = items["merchant:invalid_gtin"]
    assert gtin["severity"] == "yüksek" and gtin["owner"] == "tsoft" and gtin["count"] == 2
    assert "Invalid GTIN" in gtin["title"] and "2 ürün" in gtin["title"]
    assert "support.google.com" in gtin["detail"] and "barkod" in gtin["detail"]
    assert gtin["link"] == "/seo-geo/alisveris?merchant=invalid_gtin"
    assert "toplam satış 125" in gtin["impactBasis"]
    img = items["merchant:image_too_small"]
    assert img["severity"] == "orta" and "1 ürün T-soft ürünüyle eşlenemedi" in img["detail"]


def test_worklist_source_without_table_is_empty():
    assert w.src_merchant(_Env(sa.create_engine("sqlite://"))) == []
