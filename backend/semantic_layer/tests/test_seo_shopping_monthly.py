"""SEO & GEO → Google Alışveriş hazırlığı (seo_geo/shopping.py) ve aylık yönetim raporu (seo_geo/monthly.py).
Düz veriyle: GTIN sağlaması, başlık kuralları, fiyat/stok alan adı çeşitleri, besleme satırı, İstanbul ay sınırları,
PDF baytları."""
from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI

from semantic_bridge.seo_geo import features, monthly, shopping

UTC = timezone.utc
SITE = "https://timas.com.tr"


def product(**kw):
    p = {"ProductId": "11", "ProductCode": "T-11", "ProductName": "Küçük Prens", "Model": "Antoine de Saint-Exupéry",
         "Brand": "Timaş Yayınları", "Details": "<p>Bir çocuk kitabı ve çok daha fazlası.</p>", "SeoLink": "kucuk-prens",
         "ImageUrls": [{"Small": "https://cdn.x/k-s.jpg", "Big": "https://cdn.x/k-b.jpg"}, {"Big": "https://cdn.x/k2.jpg"}],
         "Barcode": "9780306406157", "SellingPriceVatIncluded": "120,50", "Stock": "7", "Currency": "TL",
         "DefaultCategoryPath": "Kitap/Çocuk"}
    p.update(kw)
    return {k: v for k, v in p.items() if v is not None}


def codes(a):
    return {i["code"] for i in a["issues"]}


# ------------------------------------------------------------------ GTIN
@pytest.mark.parametrize("code", ["9780306406157", "96385074", "036000291452", "9786052116418"[:12] +
                                  str(shopping.gtin_check_digit("978605211641"))])
def test_gtin_valid(code):
    assert shopping.gtin_valid(code)


@pytest.mark.parametrize("code", ["9780306406158", "978030640615", "12345", "97803064061X7", ""])
def test_gtin_invalid(code):
    assert not shopping.gtin_valid(code)


def test_normalize_gtin_cases():
    assert shopping.normalize_gtin("978-0-306-40615-7") == ("9780306406157", [])
    assert shopping.normalize_gtin("0-306-40615-2") == ("9780306406157", ["gtin_isbn10"])
    assert shopping.normalize_gtin("9780306406158") == (None, ["gtin_invalid"])
    assert shopping.normalize_gtin("") == (None, ["gtin_missing"])
    assert shopping.normalize_gtin("2000000000008") == (None, ["gtin_restricted"])
    assert shopping.is_book("9790306406150") and not shopping.is_book("8690000000001")


# ------------------------------------------------------------------ başlık
def test_title_rules():
    assert shopping.title_issues("") == ["title_missing"]
    assert shopping.title_issues("Küçük Prens") == []
    assert "title_caps" in shopping.title_issues("KÜÇÜK PRENS VE ARKADAŞLARI")
    assert "title_caps" not in shopping.title_issues("NASA")               # kısa: kısaltma sayılır
    assert "title_caps" not in shopping.title_issues("TÜBİTAK Bilim Kitapları Dizisi")
    assert "title_promo" in shopping.title_issues("Küçük Prens %20 indirimli")
    assert "title_promo" in shopping.title_issues("Küçük Prens — ÜCRETSİZ KARGO")
    assert "title_long" in shopping.title_issues("a" * (shopping.TITLE_MAX + 1))


def test_feed_title_adds_author_only_when_it_fits():
    assert shopping.feed_title("Küçük Prens", "Saint-Exupéry") == "Küçük Prens - Saint-Exupéry"
    assert shopping.feed_title("Saint-Exupéry'den Küçük Prens", "saint-exupéry") == "Saint-Exupéry'den Küçük Prens"
    long = "kelime " * 30
    t = shopping.feed_title(long, "Yazar")
    assert len(t) <= shopping.TITLE_MAX and not t.endswith(" ")


# ------------------------------------------------------------------ fiyat ve stok (alan adı çeşitleri)
def test_money_formats():
    assert shopping.money("1.234,50") == 1234.5
    assert shopping.money("1,234.50") == 1234.5
    assert shopping.money("45 TL") == 45.0
    assert shopping.money(12) == 12.0
    assert shopping.money("") is None and shopping.money(None) is None


def test_price_variants():
    assert shopping.price_of({"SellingPriceVatIncluded": "120,50"}) == (120.5, None)
    assert shopping.price_of({"sellingprice": "100", "vat": "10"}) == (110.0, None)       # KDV eklenir, ad harf duyarsız
    assert shopping.price_of({"Price": "80", "DiscountedSellingPrice": "60"}) == (80.0, 60.0)
    assert shopping.price_of({"Price": "0"}) == (0.0, None)
    assert shopping.price_of({}) == (None, None)


def test_availability_variants():
    assert shopping.availability({"Stock": "7"}) == "in_stock"
    assert shopping.availability({"stockcount": 0}) == "out_of_stock"
    assert shopping.availability({"StockAmount": "0,00"}) == "out_of_stock"
    assert shopping.availability({}) is None


def test_currency():
    assert shopping.currency_of({}) == "TRY"
    assert shopping.currency_of({"Currency": "TL"}) == "TRY"
    assert shopping.currency_of({"CurrencyCode": "usd"}) == "USD"


# ------------------------------------------------------------------ denetim ve besleme satırı
def test_ready_product_row():
    a = shopping.audit(product(), SITE)
    assert a["status"] == shopping.STATUS_READY, a["issues"]
    r = a["row"]
    assert r["id"] == "T-11"
    assert r["title"] == "Küçük Prens - Antoine de Saint-Exupéry"
    assert r["description"] == "Bir çocuk kitabı ve çok daha fazlası."
    assert r["link"] == "https://timas.com.tr/kucuk-prens"
    assert r["image_link"] == "https://cdn.x/k-b.jpg" and r["additional_image_link"] == "https://cdn.x/k2.jpg"
    assert r["availability"] == "in_stock" and r["price"] == "120.50 TRY" and r["sale_price"] == ""
    assert r["gtin"] == "9780306406157" and r["identifier_exists"] == "yes"
    assert r["google_product_category"] == shopping.BOOK_CATEGORY and r["condition"] == "new"
    assert r["brand"] == "Timaş Yayınları" and r["product_type"] == "Kitap > Çocuk"


def test_blockers_and_problems():
    a = shopping.audit(product(Details="", ImageUrls=None, ImageUrl="img/no-image.jpg", Stock=None, SellingPriceVatIncluded="0"), SITE)
    assert {"desc_missing", "image_placeholder", "stock_unknown", "price_zero"} <= codes(a)
    assert a["status"] == shopping.STATUS_BLOCKED

    b = shopping.audit(product(Barcode=None, ProductName="KÜÇÜK PRENS KİTABI"), SITE)
    assert {"gtin_missing", "title_caps"} <= codes(b) and b["status"] == shopping.STATUS_PROBLEM
    assert b["row"]["identifier_exists"] == "no" and b["row"]["google_product_category"] == ""


def test_sale_price_above_price_is_dropped():
    a = shopping.audit(product(SellingPriceVatIncluded="50", DiscountedSellingPriceVatIncluded="70"), SITE)
    assert "sale_above_price" in codes(a) and a["row"]["sale_price"] == ""
    ok = shopping.audit(product(SellingPriceVatIncluded="50", DiscountedSellingPriceVatIncluded="40"), SITE)
    assert ok["row"]["sale_price"] == "40.00 TRY"


def test_out_of_stock_is_info_only():
    a = shopping.audit(product(Stock="0"), SITE)
    assert "out_of_stock" in codes(a) and a["status"] == shopping.STATUS_READY
    assert a["row"]["availability"] == "out_of_stock"


def test_crm_flag_and_duplicates():
    ps = [product(), product(ProductId="12", ProductCode="T-12"), product(ProductId="13", Barcode="9780306406158")]
    dups = shopping.duplicate_gtins(ps)
    assert dups == {"9780306406157"}
    a = shopping.audit(ps[0], SITE, crm_flag="cekildi", duplicate_gtins=dups)
    assert {"crm_flag", "gtin_duplicate"} <= codes(a) and a["status"] == shopping.STATUS_BLOCKED
    assert "gtin_invalid" in codes(shopping.audit(ps[2], SITE))


def test_non_book_needs_brand():
    a = shopping.audit(product(Barcode="8690000000001"[:12] + str(shopping.gtin_check_digit("869000000000")), Brand=None), SITE)
    assert {"not_book", "brand_missing"} <= codes(a)
    b = shopping.audit(product(Brand=None), SITE)
    assert "brand_missing_book" in codes(b) and b["status"] == shopping.STATUS_READY


def test_long_description_clipped():
    a = shopping.audit(product(Details="söz " * 2000), SITE)
    assert "desc_long" in codes(a) and len(a["row"]["description"]) <= shopping.DESC_MAX


def test_feed_tsv_has_header_and_no_tabs_in_values():
    row = shopping.audit(product(Details="satır\tbir\nsatır iki"), SITE)["row"]
    tsv = shopping.feed_tsv([row])
    lines = tsv.rstrip("\n").split("\n")
    assert lines[0].split("\t") == list(shopping.FEED_COLUMNS)
    assert len(lines) == 2 and len(lines[1].split("\t")) == len(shopping.FEED_COLUMNS)
    assert "satır bir satır iki" in lines[1]


def test_summarize_counts():
    res = [{"status": "hazir", "issues": []},
           {"status": "sorunlu", "issues": [{"code": "gtin_missing"}, {"code": "gtin_missing"}]},
           {"status": "engelleyici", "issues": [{"code": "price_zero"}]}]
    s = shopping.summarize(res)
    assert (s["products"], s["ready"], s["problem"], s["blocked"]) == (3, 1, 1, 1)
    by = {i["code"]: i["count"] for i in s["issues"]}
    assert by["gtin_missing"] == 1 and by["price_zero"] == 1
    assert s["issues"][0]["severity"] == shopping.BLOCKER


# ------------------------------------------------------------------ ay sınırları (İstanbul)
def test_previous_month_istanbul_boundaries():
    assert monthly.previous_month(datetime(2026, 9, 30, 20, 59, tzinfo=UTC)) == "2026-08"   # İstanbul 23:59, 30 Eylül
    assert monthly.previous_month(datetime(2026, 9, 30, 21, 1, tzinfo=UTC)) == "2026-09"    # İstanbul 00:01, 1 Ekim
    assert monthly.is_first_day(datetime(2026, 9, 30, 21, 1, tzinfo=UTC))
    assert not monthly.is_first_day(datetime(2026, 9, 30, 20, 59, tzinfo=UTC))
    assert monthly.previous_month(datetime(2026, 1, 1, 9, 0, tzinfo=UTC)) == "2025-12"


def test_month_math():
    assert monthly.month_bounds("2028-02") == (date(2028, 2, 1), date(2028, 2, 29))
    assert monthly.month_bounds("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
    assert monthly.shift("2026-01", -1) == "2025-12" and monthly.shift("2026-08", -12) == "2025-08"
    assert monthly.shift("2025-12", 1) == "2026-01"
    a, b = monthly.month_range_utc("2026-09")
    assert a == datetime(2026, 8, 31, 21, 0, tzinfo=UTC) and b == datetime(2026, 9, 30, 21, 0, tzinfo=UTC)
    assert monthly.month_label("2026-08") == "Ağustos 2026"
    with pytest.raises(ValueError):
        monthly.month_bounds("2026-13")


def test_buildable_and_gsc_complete():
    at = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)
    assert monthly.buildable("2026-09", at) and monthly.buildable("2025-01", at)
    assert not monthly.buildable("2026-10", at) and not monthly.buildable("2026-9", at)
    assert not monthly.gsc_complete("2026-09", at)                        # 30 Eylül henüz kesin değil
    assert monthly.gsc_complete("2026-09", datetime(2026, 10, 3, 9, 0, tzinfo=UTC))


# ------------------------------------------------------------------ hesaplar
def test_totals_weighted_position_and_change():
    t = monthly.totals([{"clicks": 10, "impressions": 100, "position": 2.0},
                        {"clicks": 30, "impressions": 300, "position": 6.0}])
    assert t["clicks"] == 40 and t["impressions"] == 400 and t["ctr"] == pytest.approx(0.1)
    assert t["position"] == pytest.approx(5.0)
    assert monthly.totals([{"clicks": 1, "impressions": 2}])["position"] is None
    assert monthly.totals([]) is None
    assert monthly.change(110, 100) == pytest.approx(0.1) and monthly.change(5, 0) is None


def test_movers_and_book_share():
    mv = monthly.movers([{"keys": ["a"], "clicks": 10}, {"keys": ["b"], "clicks": 5}],
                        [{"keys": ["a"], "clicks": 4}, {"keys": ["c"], "clicks": 9}], top=1)
    assert mv["gainers"][0]["key"] == "c" and mv["losers"][0]["key"] == "a"
    assert mv["gainersTotal"] == 1 and mv["losersTotal"] == 2 and len(mv["losers"]) == 1
    s = monthly.book_share([(100, 90), (50, 70), (10, 85), (0, 95)], top=2)
    assert s["counted"] == 2 and s["good"] == 1 and s["share"] == 0.5
    assert s["active"] == 4 and s["activeGood"] == 3


def fake_summary():
    cur = {"month": "2026-08", "available": True, "source": "google", "clicks": 12345, "impressions": 456789,
           "ctr": 0.027, "position": 11.4, "days": 31}
    prev = {**cur, "month": "2026-07", "clicks": 11000, "impressions": 400000, "ctr": 0.0275, "position": 12.0}
    s = {"month": "2026-08", "label": "Ağustos 2026", "generatedAt": "2026-09-04T01:00:00+00:00", "complete": True,
         "google": {"current": cur, "previous": prev, "lastYear": {"month": "2025-08", "available": False, "reason": "Veri yok."},
                    "daily": [{"d": f"2026-08-{d:02d}", "clicks": 300 + d * 5, "impressions": 9000} for d in range(1, 32)]},
         "queries": {"available": True, "top": 10, "gainersTotal": 1, "losersTotal": 1,
                     "gainers": [{"key": "küçük prens", "clicks": 90, "prevClicks": 40, "delta": 50}],
                     "losers": [{"key": "şiir kitapları " * 12, "clicks": 10, "prevClicks": 30, "delta": -20}]},
         "pages": {"available": False, "reason": "Veri yok."},
         "books": monthly.book_share([(100, 90), (50, 70)]),
         "proposals": {"created": 12, "approved": 8, "rejected": 1, "pending": 3},
         "crm": {"available": True, "rights": {"var": 900, "eksik": 12}, "flags": {"cekildi": 3},
                 "labels": {"var": "Hak var", "eksik": "Hak eksik"}, "flagLabels": {"cekildi": "CRM'de: satıştan çekildi"}},
         "tech": {"available": True, "checked": 2000, "issues": [{"id": "not_found", "title": "Sayfa bulunamadı (404/410)",
                                                                   "severity": "kritik", "count": 4, "previous": 7}]},
         "geo": {"engines": [{"engine": "gemini", "label": "Gemini (Google)", "measured": 40, "mentioned": 12, "cited": 4,
                              "mentionRate": 0.3, "citeRate": 0.1}], "previous": []},
         "alerts": {"available": True, "open": 2, "bySeverity": {"kritik": 1, "orta": 1}, "openedInMonth": 5,
                    "resolvedInMonth": 3, "items": [{"id": "x", "severity": "kritik", "title": "Tıklama düştü",
                                                     "link": None, "firstSeen": None}] * 25},
         "worklist": {"available": True, "total": 40, "byStatus": {"acik": 30, "bitti": 10}, "changedInMonth": 9}}
    s["kpi"] = monthly.kpi(s)
    s["trend"] = [{"month": "2026-07", "clicks": 11000}, {"month": "2026-08", **s["kpi"]}]
    return s


def test_kpi_from_summary():
    k = fake_summary()["kpi"]
    assert k["clicks"] == 12345 and k["share80"] == 0.5 and k["techIssues"] == 4
    assert k["geoMention"] == pytest.approx(0.3) and k["alertsOpen"] == 2


def test_pdf_builder_outputs_pdf():
    pytest.importorskip("fpdf")
    out = monthly.render_pdf(fake_summary())
    assert isinstance(out, bytes) and out.startswith(b"%PDF") and len(out) > 2000


def test_pdf_builder_with_no_data():
    pytest.importorskip("fpdf")
    s = {"month": "2026-08", "generatedAt": None, "complete": False,
         "google": {"current": {"available": False, "reason": "Veri yok."}}, "queries": {"available": False},
         "pages": {"available": False}, "books": {"counted": 0}, "proposals": {}, "crm": {"available": False},
         "tech": {"available": False}, "geo": {"engines": []}, "alerts": {"available": False},
         "worklist": {"available": False}, "trend": []}
    assert monthly.render_pdf(s).startswith(b"%PDF")


def test_mail_text():
    subject, text = monthly.render_mail(fake_summary())
    assert "Ağustos 2026" in subject and "12.345" in text and "+%12,2" in text


def test_send_without_recipients_is_screen_only():
    assert monthly.send_pdf_mail([], "s", "t", b"%PDF", "a.pdf") == "no_recipient"


# ------------------------------------------------------------------ uçlar
class _Seo:
    def __init__(self):
        self.nightly = []

    def conf(self, key):
        return ""


def test_routes_and_nightly_registered():
    app, seo = FastAPI(), _Seo()
    ctx = features.Ctx(seo=seo, gate=lambda r: "t", approver=lambda r: "t", authorize=lambda r: None)
    shopping.register(app, ctx)
    monthly.register(app, ctx)
    paths = {(tuple(sorted(r.methods)), r.path) for r in app.routes if hasattr(r, "methods")}
    for m, p in ((("GET",), "/api/v1/seo-geo/shopping"), (("GET",), "/api/v1/seo-geo/shopping/feed.tsv"),
                 (("GET",), "/api/v1/seo-geo/monthly"), (("GET",), "/api/v1/seo-geo/monthly/{month}.pdf"),
                 (("POST",), "/api/v1/seo-geo/monthly/build"), (("POST",), "/api/v1/seo-geo/monthly/{month}/send")):
        assert (m, p) in paths, p
    assert [n for n, _ in seo.nightly] == ["monthly"]
