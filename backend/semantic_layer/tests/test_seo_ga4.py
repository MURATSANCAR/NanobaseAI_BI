"""Aramadan satışa (Google Analytics): ayrıştırma, sayfalama, yol ve Search Console birleşimi, ürün eşleme, özet/değişim,
`(not set)` ayrı satır, eşikler, eylem kartları (her neden türü), iş listesi kaynağı, etki ölçümü, belirteç sızmaz."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge.seo_geo import ga4 as g
from semantic_bridge.seo_geo import ga4_actions as a
from semantic_bridge.seo_geo import worklist as w
from semantic_bridge.seo_geo.store import PRODUCTS

AT = datetime(2026, 9, 29, 3, tzinfo=timezone.utc)


def _row(dim, sessions, carts=0, purchases=0, revenue=0.0, engaged=0):
    return {"dimensionValues": [{"value": dim}],
            "metricValues": [{"value": str(v)} for v in (sessions, engaged, carts, purchases, revenue)]}


def _parsed(dim, sessions, carts=0, purchases=0, revenue=0.0):
    return g.parse_rows({"rows": [_row(dim, sessions, carts, purchases, revenue)]})[0]


# ------------------------------------------------------------------------------------------------ saf işlevler
def test_norm_path():
    assert g.norm_path("https://www.timas.com.tr/Gizli-Dedektifler-Okulu/?utm=1#x") == "gizli-dedektifler-okulu"
    assert g.norm_path("/gizli-dedektifler-okulu") == "gizli-dedektifler-okulu"
    assert g.norm_path("/9-12-yas?sayfa=2") == "9-12-yas"
    assert g.norm_path("/%C3%A7ocuk") == "çocuk"
    assert g.norm_path("/") == "" and g.norm_path("https://timas.com.tr") == ""
    assert g.norm_path("(not set)") == g.NOT_SET
    assert g.display_path("") == "/" and g.display_path("kitap") == "/kitap" and g.display_path(g.NOT_SET) == g.NOT_SET


def test_parse_rows_reads_five_metrics():
    r = _parsed("/kitap", 10, 3, 1, 125.5)
    assert r["dims"] == ["/kitap"]
    assert r["m"] == {"sessions": 10.0, "engaged": 0.0, "carts": 3.0, "purchases": 1.0, "revenue": 125.5}


def test_report_body_organic_and_extra_filter():
    b = g.report_body("2026-09-01", "2026-09-28", ["landingPage"])
    assert b["dimensionFilter"]["filter"]["stringFilter"]["value"] == "Organic Search"
    assert [m["name"] for m in b["metrics"]] == list(g.METRICS)
    b2 = g.report_body("2026-09-01", "2026-09-28", ["landingPage"], extra_filter=g.page_filter("https://timas.com.tr/kitap/"))
    exprs = b2["dimensionFilter"]["andGroup"]["expressions"]
    assert exprs[1]["filter"]["inListFilter"]["values"] == ["/kitap", "/kitap/"]
    assert "dimensionFilter" not in g.report_body("2026-09-01", "2026-09-28", ["date"], organic=False)


def test_run_report_pages_until_row_count():
    rows = [_row(f"/k{i}", i + 1) for i in range(5)]
    offsets = []

    def post(url, body):
        assert url.endswith("properties/347043165:runReport") and body["limit"] == g.PAGE_LIMIT
        offsets.append(body["offset"])
        return {"rows": rows[body["offset"]:body["offset"] + 2], "rowCount": 5}

    out = g.run_report("347043165", {"dimensions": []}, post)
    assert len(out) == 5 and offsets == [0, 2, 4]
    assert [r["dims"][0] for r in out] == [f"/k{i}" for i in range(5)]


def test_run_report_raises_when_google_stops_early():
    def post(url, body):
        return {"rows": [_row("/a", 1)] if body["offset"] == 0 else [], "rowCount": 3}

    with pytest.raises(RuntimeError):
        g.run_report("1", {}, post)


def test_run_report_empty():
    assert g.run_report("1", {}, lambda u, b: {"rowCount": 0}) == []


def test_sharp_drop_accounts_for_site_trend_and_noise():
    assert g.sharp_drop(100, 30, 1.0)
    assert not g.sharp_drop(100, 70, 1.0)
    assert not g.sharp_drop(100, 50, 0.5)          # site de yarıya indi: sayfaya özgü düşüş yok
    assert not g.sharp_drop(4, 1, 1.0)             # 4 → 1: fark gürültüden büyük değil
    assert not g.sharp_drop(0, 0, 1.0)
    assert not g.sharp_drop(900, 1010, 3.0)        # ziyaret arttı: site daha çok büyüse de «düştü» denmez


def test_quantile():
    assert g.quantile([], 0.75) == 0.0
    assert g.quantile([1, 2, 3, 4, 5], 0.75) == 4.0


# ------------------------------------------------------------------------------------------------ birleşim
def _raw():
    return {
        "pagesCur": [_parsed("/kitap-a", 1000, 200, 0, 0), _parsed("/Kitap-A/", 10, 1, 0, 0), _parsed("/kitap-b", 400, 80, 8, 1600),
                     _parsed("/9-12-yas", 300, 10, 1, 150), _parsed("/", 500, 5, 2, 300), _parsed("(not set)", 700, 20, 3, 450)],
        "pagesPrev": [_parsed("/kitap-a", 900, 150, 0, 0), _parsed("/kitap-c", 600, 40, 6, 1200), _parsed("/kitap-b", 50, 5, 1, 200),
                      _parsed("/9-12-yas", 20, 1, 0, 0), _parsed("/", 30, 1, 0, 0)],
        "channelsCur": [_parsed("Organic Search", 2910, 316, 14, 2500), _parsed("Direct", 1000, 100, 10, 3000)],
        "channelsPrev": [_parsed("Organic Search", 1500, 190, 10, 2000), _parsed("Direct", 1000, 100, 10, 3000)],
        "daily": [_parsed("20260928", 100, 10, 1, 50.0), _parsed("20260927", 90, 9, 0, 0)],
    }


GSC = {"cur": [{"keys": ["https://www.timas.com.tr/kitap-a"], "clicks": 700, "impressions": 9000, "position": 4.0},
               {"keys": ["https://www.timas.com.tr/kitap-a/"], "clicks": 50, "impressions": 1000, "position": 8.0},
               {"keys": ["https://www.timas.com.tr/kitap-d"], "clicks": 30, "impressions": 300, "position": 9.0},
               {"keys": ["https://www.timas.com.tr/yalniz-gosterim"], "clicks": 0, "impressions": 50, "position": 30.0}],
       "prev": [{"keys": ["https://www.timas.com.tr/kitap-a"], "clicks": 600, "impressions": 8000, "position": 5.0}],
       "error": None}
PRODS = {"kitap-a": ("p1", "Kitap A"), "kitap-b": ("p2", "Kitap B"), "kitap-c": ("p3", "Kitap C")}
LINKS = {"9-12-yas": ("category", "9-12 Yaş")}


def test_build_merges_paths_gsc_products_and_keeps_not_set_apart():
    b = g.build(_raw(), GSC, PRODS, LINKS)
    pages = {p["path"]: p for p in b["pages"]}
    a_ = pages["kitap-a"]
    assert a_["sessions"] == 1010 and a_["carts"] == 201 and a_["p_sessions"] == 900       # «/kitap-a» ve «/Kitap-A/» tek yol
    assert a_["kind"] == "urun" and a_["product_id"] == "p1" and a_["title"] == "Kitap A"
    assert a_["clicks"] == 750 and a_["impressions"] == 10000 and a_["position"] == 4.4      # gösterim ağırlıklı sıra
    assert a_["p_clicks"] == 600
    assert pages["9-12-yas"]["kind"] == "kategori" and pages["9-12-yas"]["title"] == "9-12 Yaş"
    assert pages[""]["kind"] == "diger" and pages[""]["title"] == "Anasayfa"
    ns = pages[g.NOT_SET]
    assert ns["kind"] == "belirsiz" and ns["sessions"] == 700 and ns["product_id"] is None and ns["flags"] == ""
    assert pages["kitap-c"]["sessions"] == 0 and pages["kitap-c"]["p_sessions"] == 600       # yalnız önceki dönemde
    assert pages["kitap-d"]["clicks"] == 30 and pages["kitap-d"]["sessions"] == 0            # tıklama var, ziyaret yok
    assert "yalniz-gosterim" not in pages                                                  # tıklamasız adres satır olmaz
    s = b["summary"]
    assert s["organic"]["cur"]["sessions"] == 2910 and s["organic"]["prev"]["sessions"] == 1500
    assert round(s["organic"]["change"]["revenue"], 1) == 25.0
    assert round(s["share"]["revenue"], 4) == round(2500 / 5500, 4)
    assert s["funnel"]["clicks"] == 780 and s["funnel"]["sessions"] == 2910
    assert s["pages"]["notSet"]["sessions"] == 700
    assert s["pages"]["matched"] == 3 and s["pages"]["unmatched"] == 3                       # kategori, anasayfa, kitap-d
    assert [d["day"] for d in b["daily"]] == ["2026-09-27", "2026-09-28"]
    assert b["channels"][0]["channel"] == "Organic Search" and b["channels"][0]["p_sessions"] == 1500


def test_flags_from_data_not_fixed_numbers():
    b = g.build(_raw(), GSC, PRODS, LINKS)
    pages = {p["path"]: p for p in b["pages"]}
    th = b["summary"]["thresholds"]
    # ürün sayfaları dönüşümü 8 / 1410 → 3 satış için ≈ 529 ziyaret gerekir; eşik üst çeyrekle birlikte büyük olan
    assert th["highTraffic"] >= 529 and ",satissiz," in pages["kitap-a"]["flags"]
    assert "satissiz" not in pages["kitap-b"]["flags"]
    assert "dusen_oturum" in pages["kitap-c"]["flags"] and "dusen_ciro" in pages["kitap-c"]["flags"]
    assert b["summary"]["flags"]["satissiz"] == 1


def test_gsc_failure_does_not_block():
    out = g.fetch_gsc(g.windows(date(2026, 9, 29)), query=lambda s, e, d: (_ for _ in ()).throw(RuntimeError("Bearer abc.def kırık")))
    assert out["cur"] is None and "abc.def" not in out["error"]


def test_windows():
    w_ = g.windows(date(2026, 9, 29))
    assert w_["cur"] == ["2026-09-01", "2026-09-28"] and w_["prev"] == ["2026-08-04", "2026-08-31"]
    assert w_["daily"][0] == "2026-07-01" and w_["gscCur"][1] == "2026-09-26"


# ------------------------------------------------------------------------------------------------ veritabanı
def _db(products=None):
    eng = sa.create_engine("sqlite://")
    PRODUCTS.create(eng)
    with eng.begin() as c:
        for pid, name, active, data, score, issues in products or []:
            c.execute(PRODUCTS.insert().values(tenant_id="t", product_id=pid, code=pid, name=name, active=active, score=score,
                                               issues_json=json.dumps(issues), data_json=json.dumps(data), synced_at=AT))
    return eng


def test_product_index_uses_seo_link():
    eng = _db([("p1", "Kitap A", True, {"SeoLink": "Kitap-A"}, 90, []), ("p9", "Eski A", False, {"SeoLink": "/kitap-a/"}, 90, []),
               ("p2", "Kitap B", True, {"Url": "https://timas.com.tr/kitap-b"}, 90, [])])
    idx = g.product_index(eng, "t")
    assert idx["kitap-a"] == ("p1", "Kitap A") and idx["kitap-b"] == ("p2", "Kitap B")


def test_save_query_and_product_totals():
    eng = _db()
    b = g.build(_raw(), GSC, PRODS, LINKS)
    data = g.save(eng, "t", "347043165", b, g.windows(date(2026, 9, 29)), AT)
    assert data["property"] == "347043165" and data["organic"]["cur"]["sessions"] == 2910
    snap = g.read_snap(eng, "t")
    assert snap["error"] is None and snap["thresholds"]["highTraffic"] > 0
    with eng.connect() as c:
        urun = c.execute(sa.select(g.PAGES).where(*g.page_conditions("t", kind="urun")).order_by(*g.page_order("oturum"))).mappings().all()
        flagged = c.execute(sa.select(g.PAGES).where(*g.page_conditions("t", flag="dusen"))).mappings().all()
        found = c.execute(sa.select(g.PAGES).where(*g.page_conditions("t", q="/kitap-a"))).mappings().all()
        chans = c.execute(sa.select(sa.func.count()).select_from(g.CHANNELS)).scalar()
    assert [r["path"] for r in urun] == ["kitap-a", "kitap-b", "kitap-c"]
    assert [r["path"] for r in flagged] == ["kitap-c"]
    assert [r["path"] for r in found] == ["kitap-a"] and chans == 2
    v = g.page_view(urun[0])
    assert v["path"] == "/kitap-a" and v["flags"] == ["satissiz"] and v["flagLabels"] == ["Trafik yüksek, satış yok"]
    assert round(v["change"]["sessions"], 1) == 12.2
    t = g.product_totals(eng, "t", "p1")
    assert t["cur"]["sessions"] == 1010 and t["paths"] == ["/kitap-a"] and t["flags"] == ["satissiz"]
    assert g.product_totals(eng, "t", "yok") is None
    with pytest.raises(Exception):
        g.page_conditions("t", kind="bilinmeyen")
    with pytest.raises(Exception):
        g.page_order("hepsi")


def test_save_error_keeps_data_and_hides_token():
    eng = _db()
    g.save(eng, "t", "1", g.build(_raw(), GSC, PRODS, LINKS), g.windows(date(2026, 9, 29)), AT)
    g.save_error(eng, "t", "Google 401: ya29.gizli-belirtec Bearer abc.def", AT)
    snap = g.read_snap(eng, "t")
    assert "ya29" not in snap["error"] and "abc.def" not in snap["error"]
    assert snap["organic"]["cur"]["sessions"] == 2910
    with eng.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(g.PAGES)).scalar() > 0


# ------------------------------------------------------------------------------------------------ eylem kartları
TH = {"highTraffic": 300, "q3": 50, "conv": 0.01, "cartRate": 0.2, "purchasePerCart": 0.1, "aov": 200.0, "q3Prev": 50,
      "sessionRatio": 1.0, "purchaseRatio": 1.0, "revenueRatio": 1.0, "clickRatio": 1.0}


def _item(key="kitap-a", pid="p1", sessions=1000, carts=200, purchases=0, revenue=0.0, prev=None, flags=(),
          clicks=None, prev_clicks=None, kind="urun"):
    cur = {"sessions": sessions, "engaged": 0, "carts": carts, "purchases": purchases, "revenue": revenue}
    pv = prev or {"sessions": sessions, "engaged": 0, "carts": carts, "purchases": purchases, "revenue": revenue}
    return {"path": "/" + key, "key": key, "kind": kind, "kindLabel": "Ürün", "productId": pid, "title": "Kitap A",
            "cur": cur, "prev": pv, "change": {}, "clicks": clicks, "impressions": 1000 if clicks else None, "position": 9.0 if clicks else None,
            "prevClicks": prev_clicks, "prevImpressions": 1200 if prev_clicks else None, "prevPosition": 4.0 if prev_clicks else None,
            "conv": purchases / sessions if sessions else None, "flags": list(flags), "flagLabels": []}


def _ctx(products=None, similar=None):
    ctx = a.Context(sa.create_engine("sqlite://"), "t", lambda k: "", TH, "https://timas.com.tr", similar)
    for pid, p in (products or {}).items():
        ctx.products[pid] = {"name": p.get("name", pid), "active": p.get("active", True), "data": p.get("data", {}),
                             "score": p.get("score", 90), "issues": p.get("issues", []), "syncedAt": AT}
    return ctx


def _codes(cards):
    return [c["code"] for c in cards]


def _shape(c):
    assert set(c) >= {"code", "badge", "tone", "severity", "title", "why", "changeHeads", "changes", "steps", "owner",
                      "ownerLabel", "impact", "priority", "priorityBasis", "links"}
    assert 2 <= len(c["steps"]) <= 5 and c["why"] and c["ownerLabel"]
    if c["impact"]:
        assert c["impact"]["value"] > 0 and "≈" in c["impact"]["formula"] or "risk" in c["impact"]["formula"]


class _Sim:
    def result(self):
        return {"byId": {"p1": {"suggestions": [
            {"id": "p5", "name": "Yok Kitap", "url": "https://timas.com.tr/yok-kitap", "reasonText": "Aynı yazar"},
            {"id": "p6", "name": "Var Kitap", "url": "https://timas.com.tr/var-kitap", "reasonText": "CRM emsal kitap"}]}}}


def test_card_stock_out_with_redirect_candidates():
    ctx = _ctx({"p1": {"data": {"Stock": 0, "CountTotalSales": 40}}, "p5": {"data": {"Stock": 0}}, "p6": {"data": {"Stock": 12}}}, _Sim())
    cs = a.cards(_item(carts=5), ctx)
    c = next(x for x in cs if x["code"] == "stok_yok")
    _shape(c)
    assert c["owner"] == "tsoft" and "T-soft stok 0" in c["why"] and "1.000 organik ziyaret" in c["why"]
    assert [x["proposed"].split(" — ")[0] for x in c["changes"]] == ["/var-kitap"] and c["changes"][0]["current"] == "/kitap-a"
    assert c["impact"] and "organik dönüşüm" in c["impact"]["formula"]
    # liste görünümünde (detail=False) benzer kitap okunmaz
    assert next(x for x in a.cards(_item(carts=5), ctx, detail=False) if x["code"] == "stok_yok")["changes"] == []


def test_card_not_on_sale():
    cs = a.cards(_item(carts=5), _ctx({"p1": {"active": False, "data": {"Stock": 5}}}))
    assert "satista_degil" in _codes(cs)


def test_card_search_drop():
    cs = a.cards(_item(carts=250, purchases=10, revenue=2000, clicks=100, prev_clicks=400), _ctx({"p1": {"data": {"Stock": 5}}}))
    c = next(x for x in cs if x["code"] == "arama_dustu")
    _shape(c)
    assert c["changeHeads"] == ["Önceki 28 gün", "Bu dönem"] and c["changes"][0]["current"] == "400"
    assert "4.0 → 9.0" in c["why"] and c["impact"]["value"] == 300 * 0.01 * 200


def test_card_tech_and_index_and_rich():
    ctx = _ctx({"p1": {"data": {"Stock": 5}}})
    ctx.tech_pid["p1"] = {"url": "https://timas.com.tr/kitap-a", "status": 404, "chain": [], "issues": ["not_found", "img_no_alt"]}
    ctx.insp_pid["p1"] = {"url": "https://timas.com.tr/kitap-a", "status": "crawled_not_indexed", "coverage": "Crawled - currently not indexed",
                          "error": None, "lastCrawl": AT,
                          "rich": {"issues": [{"type": "Product snippets", "message": 'Missing field "shippingDetails"', "severity": "WARNING"},
                                              {"type": "Product snippets", "message": 'Missing field "aggregateRating"', "severity": "ERROR"}]}}
    cs = {c["code"]: c for c in a.cards(_item(carts=250, purchases=10, revenue=2000), ctx)}
    t = cs["teknik"]
    _shape(t)
    assert t["severity"] == "kritik" and "Sayfa bulunamadı" in t["title"] and len(t["changes"]) == 1
    assert any("yönlendirme girin" in s for s in t["steps"]) and t["links"][0]["to"] == "/seo-geo/teknik"
    assert "risk" in t["impact"]["formula"]
    d = cs["dizin"]
    assert d["changes"][0]["current"] == "Tarandı ama dizinde değil" and d["severity"] == "yüksek"
    r = cs["zengin_sonuc"]
    assert [x["label"] for x in r["changes"]] == ["shippingDetails", "aggregateRating"]
    assert "kargo" in r["changes"][0]["proposed"] and r["severity"] == "yüksek"
    assert r["links"][0]["to"] == "/seo-geo/google-taramasi?filtre=rich"


def test_card_merchant():
    ctx = _ctx({"p1": {"data": {"Stock": 5}}})
    ctx.merchant["p1"] = [{"offerId": "p1", "status": "onaylanmayan", "issues": [
        {"code": "invalid_gtin", "severity": "DISAPPROVED", "description": "Invalid GTIN", "detail": "Use a valid GTIN",
         "attribute": "gtins", "resolution": "merchant_action", "documentation": "https://support.google.com/merchants/answer/6239388"},
        {"code": "missing_shipping_weight", "severity": "NOT_IMPACTED", "description": "Missing shipping weight"}]}]
    c = next(x for x in a.cards(_item(carts=250, purchases=10, revenue=2000), ctx) if x["code"] == "merchant")
    _shape(c)
    assert len(c["changes"]) == 1 and "barkod (GTIN)" in c["changes"][0]["label"]
    assert c["changes"][0]["proposed"].startswith("Düzeltme bizde") and c["changes"][0]["doc"].startswith("https://support.google")
    assert c["links"][0]["to"] == "/seo-geo/alisveris?merchant=invalid_gtin" and c["severity"] == "yüksek"


def test_card_content_uses_existing_proposal_and_limits():
    ctx = _ctx({"p1": {"score": 40, "data": {"Stock": 5, "SeoTitle": "Kısa", "Details": "bir iki üç"},
                       "issues": [{"rule": "desc_short", "title": "Ürün açıklaması kısa"}]}})
    ctx.proposals["p1"] = {"id": "x", "status": "hazir", "fields": {"SeoTitle": "Kitap A — Yazar | Timaş Yayınları"}}
    c = next(x for x in a.cards(_item(carts=250, purchases=10, revenue=2000), ctx) if x["code"] == "icerik")
    _shape(c)
    title, meta, desc = c["changes"]
    assert title["current"] == "Kısa" and title["proposed"] == "Kitap A — Yazar | Timaş Yayınları" and title["ok"] is False
    assert "kural 30–65" in title["label"] and meta["proposed"].startswith("Zeki AI önerisi yok")
    assert desc["current"] == "3 kelime" and desc["ok"] is False and c["owner"] == "icerik" and c["severity"] == "yüksek"
    assert "onay bekleyen" in c["why"] and c["links"][0]["kind"] == "propose"


def test_card_cart_funnel_checklist():
    ctx = _ctx({"p1": {"data": {"Stock": 5, "SellingPrice": 100, "Details": "kısa"}, "issues": [{"rule": "image_missing", "title": "Ürün görseli yok"}]}})
    c = next(x for x in a.cards(_item(sessions=1000, carts=20, purchases=1, revenue=150), ctx) if x["code"] == "sepete_eklenmiyor")
    _shape(c)
    rows = {x["label"]: x for x in c["changes"]}
    assert rows["Sepete ekleme oranı"]["current"] == "%2,0" and rows["Ürün açıklaması"]["ok"] is False
    assert rows["Görsel"]["ok"] is False and "Ürün görseli yok" in rows["Görsel"]["current"]
    assert rows["Stok"]["ok"] is True and "İndirim yok" in rows["Fiyat"]["proposed"]
    assert c["impact"]["value"] == pytest.approx((1000 * 0.2 - 20) * 0.1 * 200)


def test_card_checkout():
    ctx = _ctx({"p1": {"data": {"Stock": 5}}})
    c = next(x for x in a.cards(_item(sessions=200, carts=50, purchases=0), ctx) if x["code"] == "odeme")
    _shape(c)
    assert c["owner"] == "tsoft" and "≈5 satış" in c["why"] and c["impact"]["value"] == pytest.approx(50 * 0.1 * 200)
    # beklenen satış 3'ün altındaysa kart yok
    assert "odeme" not in _codes(a.cards(_item(sessions=200, carts=20, purchases=0), ctx))


def test_general_cards_when_nothing_explains():
    ctx = _ctx({"p1": {"data": {"Stock": 5}}})
    drop = a.cards(_item(sessions=100, carts=20, purchases=2, revenue=400, flags=["dusen_oturum"],
                         prev={"sessions": 900, "engaged": 0, "carts": 90, "purchases": 9, "revenue": 1800}), ctx)
    assert _codes(drop) == ["dusen_genel"]
    _shape(drop[0])
    assert drop[0]["impact"]["value"] == pytest.approx(1400) and drop[0]["changeHeads"] == ["Önceki 28 gün", "Son 28 gün"]
    quiet_ctx = _ctx({"p1": {"data": {"Stock": 5}}})
    quiet_ctx.th = {**TH, "purchasePerCart": None}   # sepet adımı hesaplanamıyor: ödeme kartı çıkmaz
    quiet = a.cards(_item(sessions=500, carts=100, purchases=0, flags=["satissiz"]), quiet_ctx)
    assert _codes(quiet) == ["satissiz_genel"]
    assert a.cards(_item(sessions=100, carts=20, purchases=2, revenue=400), ctx) == []   # bayraksız, nedensiz: kart yok
    assert a.cards(_item(key=g.NOT_SET, kind="belirsiz", pid=None), ctx) == []


def test_cards_sorted_by_priority():
    ctx = _ctx({"p1": {"data": {"Stock": 0}}})
    ctx.tech_pid["p1"] = {"url": "u", "status": 404, "chain": [], "issues": ["not_found"]}
    cs = a.cards(_item(carts=5), ctx, detail=False)
    assert [c["priority"] for c in cs] == sorted((c["priority"] for c in cs), reverse=True)
    assert "beklenen etki" in cs[0]["priorityBasis"]


# ------------------------------------------------------------------------------------------------ Zeki AI özeti
class _Llm:
    def __init__(self, text):
        self.text = text

    def chat(self, messages, **kw):
        return self.text


class _Rt:
    def __init__(self, text):
        self.llm = _Llm(text)

    def llm_for(self, module, priority=None):
        assert module == "seo"
        return self.llm


class _SeoRt:
    def __init__(self, text):
        self.rt = _Rt(text)

    def runtime(self):
        return self.rt


def test_zeki_summary_drops_foreign_numbers():
    ctx = _ctx({"p1": {"data": {"Stock": 0}}})
    it = _item(carts=5)
    facts = a.summary_facts(it, a.cards(it, ctx, detail=False))
    ok = a.zeki_summary(_SeoRt("Sayfa 1.000 ziyaret aldı ama stok 0. Önce yönlendirme yapılmalı."), facts)
    assert ok["source"] == "zeki" and ok["text"].startswith("Sayfa 1.000")
    bad = a.zeki_summary(_SeoRt("Sayfa 7.777 ziyaret aldı."), facts)
    assert bad["text"] is None


# ------------------------------------------------------------------------------------------------ iş listesi
class _SeoConf:
    def conf(self, key):
        return ""


class _Env:
    def __init__(self, eng):
        self.eng, self.tenant, self.seo = eng, "t", _SeoConf()

    def has(self, table):
        return sa.inspect(self.eng).has_table(table.name)

    def products(self):
        return {"p1": {"sales": 120.0}, "p3": {"sales": 50.0}}


def test_worklist_source_one_item_per_flagged_page_with_cards():
    eng = _db([("p1", "Kitap A", True, {"SeoLink": "kitap-a", "Stock": 0}, 90, []),
               ("p3", "Kitap C", True, {"SeoLink": "kitap-c", "Stock": 4}, 90, [])])
    g.save(eng, "t", "1", g.build(_raw(), GSC, PRODS, LINKS), g.windows(date(2026, 9, 29)), AT)
    items = {i["ref"]: i for i in w.src_ga4(_Env(eng))}
    assert set(items) == {"ga4:sayfa:kitap-a", "ga4:sayfa:kitap-c"}
    a_ = items["ga4:sayfa:kitap-a"]
    assert a_["source"] == "ga4" and a_["owner"] == "tsoft" and a_["productId"] == "p1"
    assert a_["link"] == "/seo-geo/aramadan-satisa?sayfa=/kitap-a"
    assert "Trafik yüksek, satış yok" in a_["title"] and "Stokta olmayan kitabın sayfasını" in a_["detail"]
    assert "Adımlar: 1." in a_["detail"] and a_["group"][0] == "ga4_satissiz"
    c = items["ga4:sayfa:kitap-c"]
    assert c["severity"] == "yüksek" and c["group"][0] == "ga4_dusen"
    assert w.SOURCES["ga4"] == "Aramadan satış fırsatları"


def test_worklist_source_without_table_is_empty():
    assert w.src_ga4(_Env(sa.create_engine("sqlite://"))) == []


# ------------------------------------------------------------------------------------------------ etki ölçümü
def test_measure_impact_and_impact_for():
    from semantic_bridge.seo_geo import impact as imp

    eng = _db()
    imp.IMPACT.create(eng)
    today = date(2026, 9, 29)
    with eng.begin() as c:
        c.execute(imp.IMPACT.insert().values(tenant_id="t", proposal_id="pr1", product_id="p1", url="https://timas.com.tr/kitap-a",
                                             applied_at=today - timedelta(days=40), status="tamam"))
        c.execute(imp.IMPACT.insert().values(tenant_id="t", proposal_id="pr2", product_id="p2", url="https://timas.com.tr/kitap-b",
                                             applied_at=today - timedelta(days=5), status="olculuyor"))
    calls = []

    def post(url, body):
        calls.append(body["dateRanges"][0]["startDate"])
        vals = (100, 10, 2, 400.0) if len(calls) == 1 else (150, 20, 4, 900.0)
        return {"rows": [_row("/kitap-a", vals[0], vals[1], vals[2], vals[3])], "rowCount": 1}

    assert g.measure_impact(eng, "t", "1", post, today) == (1, 0)
    got = g.impact_for(eng, "t", ["pr1", "pr2"])
    assert set(got) == {"pr1"}
    assert got["pr1"]["before"]["revenue"] == 400 and got["pr1"]["after"]["sessions"] == 150
    assert got["pr1"]["delta"]["revenue"] == pytest.approx(125.0)
    assert g.measure_impact(eng, "t", "1", post, today) == (0, 0)    # bir kez ölçülür


# ------------------------------------------------------------------------------------------------ yetki ve uçlar
def test_access_rules_cover_new_endpoints():
    from semantic_bridge import access as A

    assert A.features_for("POST", "/api/v1/seo-geo/ga4/refresh") == ["ozellik:seo.calistir"]
    assert A.features_for("POST", "/api/v1/seo-geo/ga4/page-summary") == ["ozellik:seo.oneri-uret"]
    assert A.features_for("GET", "/api/v1/seo-geo/ga4/export.csv") == ["ozellik:veri.disa-aktar"]
    assert A.features_for("GET", "/api/v1/seo-geo/ga4/pages") == []


def test_routes_registered_and_quiet_without_property():
    from fastapi import FastAPI

    from semantic_bridge.seo_geo import features

    class _Seo:
        def __init__(self):
            self.nightly = []

        def conf(self, key):
            return ""

    app, seo = FastAPI(), _Seo()
    features.register(app, features.Ctx(seo=seo, gate=lambda r: "t", approver=lambda r: "t", authorize=lambda r: None))
    paths = {(tuple(sorted(r.methods)), r.path) for r in app.routes if hasattr(r, "methods")}
    for m, p in ((("GET",), "/api/v1/seo-geo/ga4"), (("GET",), "/api/v1/seo-geo/ga4/pages"), (("GET",), "/api/v1/seo-geo/ga4/page"),
                 (("POST",), "/api/v1/seo-geo/ga4/page-summary"), (("POST",), "/api/v1/seo-geo/ga4/refresh"),
                 (("GET",), "/api/v1/seo-geo/ga4/export.csv")):
        assert (m, p) in paths, p
    dict(seo.nightly)["ga4"]()  # mülk kimliği boş: hiçbir şey yapmaz, hata vermez
