"""SEO & GEO → değişikliğin etkisi (impact.py) ve fırsat listesi (opportunities.py): saf işlevler."""
from datetime import date

from semantic_bridge.seo_geo import impact, opportunities as op


def row(q, clicks, impr, pos, page=None):
    return {"keys": [q, page] if page else [q], "clicks": clicks, "impressions": impr,
            "ctr": clicks / impr if impr else 0, "position": pos}


# ------------------------------------------------------------------ etki: eşitlik ve yayın algısı

def test_html_and_whitespace_do_not_matter():
    assert impact.same("Details", "<p>Bir  kitap&nbsp;hakkında</p>", "Bir kitap hakkında")
    assert impact.same("SeoTitle", "  Kitap - Yazar | Timaş ", "Kitap - Yazar | Timaş")
    assert not impact.same("SeoTitle", "Kitap - Yazar", "Kitap - Başka Yazar")


def test_keywords_order_case_and_spacing_do_not_matter():
    assert impact.same("SearchKeywords", "roman, Tarih,yazar", "yazar,tarih , roman")
    assert not impact.same("SearchKeywords", "roman, tarih", "roman")


def test_changed_fields_only_those_that_differ_from_before():
    fields = {"SeoTitle": "Yeni başlık", "SeoDescription": "Aynı", "Details": "", "Other": "x"}
    before = {"SeoTitle": "Eski", "SeoDescription": " Aynı "}
    assert impact.changed_fields(fields, before) == {"SeoTitle": "Yeni başlık"}


def test_applied_only_when_every_changed_field_is_live():
    wanted = {"SeoTitle": "Yeni başlık", "SeoDescription": "Yeni açıklama"}
    assert impact.is_applied({"SeoTitle": "Yeni  başlık", "SeoDescription": "<p>Yeni açıklama</p>"}, wanted)
    assert not impact.is_applied({"SeoTitle": "Yeni başlık", "SeoDescription": "Eski"}, wanted)
    assert not impact.is_applied({"SeoTitle": "x"}, {})


def test_windows_exclude_applied_day_and_wait_for_final_data():
    w = impact.windows(date(2026, 8, 1), date(2026, 9, 1))
    assert w["before"] == ["2026-07-04", "2026-07-31"]
    assert w["after"] == ["2026-08-02", "2026-08-29"]
    assert w["dueOn"] == "2026-09-01" and w["due"]
    assert not impact.windows(date(2026, 8, 1), date(2026, 8, 31))["due"]


def test_aggregate_weights_position_by_impressions():
    a = impact.aggregate([row("a", 10, 100, 2.0), row("b", 0, 300, 10.0)])
    assert a["clicks"] == 10 and a["impressions"] == 400
    assert abs(a["ctr"] - 0.025) < 1e-9 and abs(a["position"] - 8.0) < 1e-9
    assert impact.aggregate([]) == {"clicks": 0, "impressions": 0, "ctr": None, "position": None}


def test_delta_percent_points_and_position():
    d = impact.delta({"clicks": 100, "impressions": 1000, "ctr": 0.1, "position": 8.0},
                     {"clicks": 150, "impressions": 1000, "ctr": 0.15, "position": 6.5})
    assert d["clicksPct"] == 50 and d["impressionsPct"] == 0
    assert abs(d["ctrPt"] - 5) < 1e-9 and d["position"] == -1.5
    assert impact.delta({"clicks": 0, "impressions": 0, "ctr": None, "position": None},
                        {"clicks": 3, "impressions": 10, "ctr": 0.3, "position": 4})["clicksPct"] is None


def test_product_url():
    assert impact.product_url({"SeoLink": "kitap-adi"}, "https://timas.com.tr/") == "https://timas.com.tr/kitap-adi"
    assert impact.product_url({"SeoLink": "https://www.timas.com.tr/k"}, "x") == "https://www.timas.com.tr/k"
    assert impact.product_url({}, "https://timas.com.tr") is None


# ------------------------------------------------------------------ fırsatlar

def test_brand_detection_turkish_case():
    for q in ("TİMAŞ yayınları", "timas kitap", "Tımaş", "TIMAŞ"):
        assert op.is_brand(q), q
    assert not op.is_brand("osmanlı tarihi kitabı")


def test_path_key_ignores_host_scheme_slash_and_query():
    k = op.path_key("https://www.timas.com.tr/Kitap-Adi/?utm=1")
    assert k == op.path_key("http://timas.com.tr/kitap-adi") == op.path_key("kitap-adi") == "/kitap-adi"
    assert op.path_key("https://timas.com.tr/") == "/"
    assert op.path_key(None) is None


def test_ctr_curve_uses_own_data_median_and_is_non_increasing():
    rows = [row(f"q1-{i}", c, 100, 1.2) for i, c in enumerate((30, 40, 50, 60, 70))]
    rows += [row(f"q3-{i}", c, 100, 3.1) for i, c in enumerate((8, 9, 10, 11, 12))]
    rows += [row(f"q5-{i}", c, 100, 5.4) for i, c in enumerate((14, 14, 14, 14, 14))]  # 3'ten yüksek: düzeltilir
    rows += [row("timaş", 90, 100, 3.0)] * 10     # marka: eğriye girmez
    rows += [row("az", 1, 10, 3.0)] * 10           # az gösterim: girmez
    curve = op.ctr_curve(rows)
    assert curve[1]["ctr"] == 0.5 and curve[1]["measured"]
    assert curve[3]["ctr"] == 0.10 and curve[3]["samples"] == 5
    assert abs(curve[2]["ctr"] - 0.30) < 1e-9 and not curve[2]["measured"]   # 1 ile 3 arası doğrusal
    assert curve[5]["ctr"] == 0.10                                             # artmaz
    assert curve[20]["ctr"] == 0.10                                            # son bilinen değer
    assert all(curve[b]["ctr"] <= curve[b - 1]["ctr"] for b in range(2, 21))
    assert op.ctr_curve([row("x", 1, 100, 2)]) == {}


def test_classify_near_and_low_ctr():
    curve = {b: {"ctr": max(0.02, 0.3 - 0.03 * b), "samples": 5, "measured": True} for b in range(1, 21)}
    items = op.classify([
        row("yakın sorgu", 20, 1000, 7.0, "https://timas.com.tr/a"),      # yakın; 7. sıra beklenen 0.09 → 0.02 < 0.045
        row("iyi sorgu", 200, 1000, 2.0),                                  # hiçbiri
        row("uzak sorgu", 1, 1000, 30.0),                                  # sıra dışı, beklenen son değer 0.02, 0.001 < 0.01
        row("az gösterim", 0, 50, 2.0),                                    # düşük tıklama için az gösterim
    ], curve)
    by = {i["query"]: i for i in items}
    assert set(by) == {"yakın sorgu", "uzak sorgu"}
    y = by["yakın sorgu"]
    assert y["kinds"] == ["yakin", "dusuk_tiklama"]
    assert y["extraClicks"] == round(1000 * curve[3]["ctr"] - 20) and y["page"] == "https://timas.com.tr/a"
    assert by["uzak sorgu"]["kinds"] == ["dusuk_tiklama"] and by["uzak sorgu"]["extraClicks"] is None


def test_classify_without_curve_lists_near_without_estimate():
    items = op.classify([row("q", 5, 500, 6.0)], {})
    assert items[0]["kinds"] == ["yakin"] and items[0]["extraClicks"] is None


def test_rank_and_totals_split_brand():
    curve = {b: {"ctr": 0.1, "samples": 5, "measured": True} for b in range(1, 21)}
    items = op.classify([row("a", 1, 500, 5.0), row("b", 1, 900, 6.0), row("timaş c", 0, 300, 8.0)], curve)
    assert [i["query"] for i in op.rank(items, "yakin")] == ["b", "a", "timaş c"]
    t = op.totals(items)
    assert t["yakin"]["all"] == 3 and t["yakin"]["brand"] == 1 and t["yakin"]["nonBrand"] == 2
    assert t["yakin"]["clicks"] == (90 - 1) + (50 - 1)


def test_opportunity_window_ends_three_days_back():
    assert op.window(date(2026, 9, 27)) == ("2026-08-28", "2026-09-24")
