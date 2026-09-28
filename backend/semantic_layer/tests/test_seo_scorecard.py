"""Kitap SEO karnesi: not hesabı, bölüm durumları (eksik veriyle), önce yapılacak 3 iş, hata veren bölüm.
Yalnız saf işlevler; ağ ve veritabanı yok."""
import pytest

from semantic_bridge.seo_geo import scorecard as sc


def _sec(sid, status, actions=()):
    return sc.section(sid, "7", status, "özet", [("Etiket", "değer"), ("Boş", None)], [(a, None) for a in actions])


# ------------------------------------------------------------------ bölüm biçimi
def test_section_shape_fills_links_and_drops_empty_facts():
    s = sc.section("urun", "42", "dikkat", "Puan 60", [("Puan", "60"), ("Yok", None), ("Boş", "")],
                   [("Öneri isteyin", None), ("Şemaya bakın", "/seo-geo/sema"), ("", None)])
    assert s["id"] == "urun" and s["title"] == "Ürün kaydı ve öneri" and s["weight"] == sc.WEIGHTS["urun"]
    assert s["link"] == "/seo-geo/urun-denetimi?urun=42"
    assert s["facts"] == [{"label": "Puan", "value": "60"}]
    assert s["actions"] == [{"text": "Öneri isteyin", "link": "/seo-geo/urun-denetimi?urun=42"},
                            {"text": "Şemaya bakın", "link": "/seo-geo/sema"}]
    with pytest.raises(ValueError):
        sc.section("urun", "42", "harika", "x")


def test_unknown_section_carries_reason_and_no_actions():
    s = sc.unknown("hiz", "7", "Bu sayfa hız örnekleminde yok.")
    assert s["status"] == "bilinmiyor" and s["reason"] == s["summary"] and s["actions"] == []


def test_guarded_turns_any_error_into_unknown_not_500():
    def boom():
        raise RuntimeError('relation "semantic_seo_tech" does not exist')

    s = sc.guarded("teknik", "7", boom)
    assert s["status"] == "bilinmiyor" and s["id"] == "teknik" and "does not exist" not in s["summary"]


def test_every_section_has_builder_and_positive_weight():
    assert set(sc.BUILDERS) == set(sc.SECTIONS)
    assert all(w > 0 for w in sc.WEIGHTS.values())


# ------------------------------------------------------------------ not
def test_grade_is_weighted_and_skips_unknown():
    secs = [_sec("urun", "iyi"), _sec("google", "sorun"), _sec("hiz", "bilinmiyor")]
    g = sc.grade(secs, {"urun": 20, "google": 12, "hiz": 4})
    assert g["score"] == round((20 * 100 + 12 * 20) / 32)
    assert g["letter"] == "B"  # 70
    assert g["counts"]["bilinmiyor"] == 1
    assert g["coverage"] == round(32 / 36, 3) and not g["lowData"]


def test_grade_letters_and_empty():
    assert [sc.letter(x) for x in (100, 85, 84, 70, 55, 54, 0)] == ["A", "A", "B", "B", "C", "D", "D"]
    g = sc.grade([_sec("urun", "bilinmiyor")])
    assert g["score"] is None and g["letter"] is None and g["lowData"]


def test_grade_marks_low_data_when_most_weight_unknown():
    secs = [_sec("video", "iyi"), _sec("urun", "bilinmiyor")]
    g = sc.grade(secs)
    assert g["score"] == 100 and g["lowData"]


# ------------------------------------------------------------------ önce yapılacak işler
def test_top_actions_prefers_problems_then_first_action_of_each_section_then_weight():
    secs = [
        _sec("video", "sorun", ["video düzelt", "video ikinci"]),
        _sec("urun", "dikkat", ["öneri iste", "başlık"]),
        _sec("google", "sorun", ["dizine al", "canonical"]),
        _sec("sema", "iyi", ["asla seçilmez"]),
        _sec("hiz", "bilinmiyor", ["asla"]),
    ]
    top = sc.top_actions(secs)
    assert [t["text"] for t in top] == ["dizine al", "video düzelt", "canonical"]
    assert top[0]["sectionId"] == "google" and top[0]["status"] == "sorun" and top[0]["link"] == "/seo-geo/google-taramasi"


def test_top_actions_dedupes_and_may_return_fewer():
    secs = [_sec("urun", "dikkat", ["aynı iş"]), _sec("sema", "dikkat", ["aynı iş"])]
    assert [t["sectionId"] for t in sc.top_actions(secs)] == ["urun"]
    assert sc.top_actions([_sec("urun", "iyi", ["x"])]) == []


# ------------------------------------------------------------------ durum eşlemeleri
def test_product_status():
    assert sc.product_status(90, []) == "iyi"
    assert sc.product_status(90, [{"severity": "yüksek"}]) == "dikkat"
    assert sc.product_status(95, [{"severity": "kritik"}]) == "sorun"
    assert sc.product_status(60, []) == "dikkat" and sc.product_status(40, []) == "sorun"
    assert sc.product_status(None, []) == "bilinmiyor"


def test_rights_status_with_missing_crm_card():
    assert sc.rights_status(None) == "dikkat"
    assert sc.rights_status({"rights": "var"}) == "iyi"
    assert sc.rights_status({"rights": "koruma_disi"}) == "iyi"
    assert sc.rights_status({"rights": "incele"}) == "dikkat" and sc.rights_status({"rights": "yok"}) == "dikkat"
    assert sc.rights_status({"rights": "eksik"}) == "sorun"
    assert sc.rights_status({"rights": "var", "statusFlag": "cekildi"}) == "sorun"


def test_severity_status_and_flags():
    assert sc.split_flags(",no_isbn,,no_faq,") == ["no_isbn", "no_faq"] and sc.split_flags(None) == []
    assert sc.severity_status([]) == "iyi" and sc.severity_status(["düşük"]) == "iyi"
    assert sc.severity_status(["orta", "düşük"]) == "dikkat" and sc.severity_status(["yüksek", "kritik"]) == "sorun"


def test_search_links_reviews_speed_status():
    assert sc.search_status(0, 0, None, 0) == "sorun"
    assert sc.search_status(10, 500, 3.2, 0) == "iyi"
    assert sc.search_status(10, 500, 12.0, 0) == "dikkat" and sc.search_status(10, 500, 2.0, 1) == "dikkat"
    assert sc.links_status(0, 1, 3, 3, True) == "sorun"
    assert sc.links_status(5, 2, 3, 3, True) == "iyi"
    assert sc.links_status(5, 4, 3, 3, None) == "dikkat" and sc.links_status(5, 2, 3, 3, False) == "dikkat"
    assert sc.links_status(5, None, 3, 3, None) == "iyi"  # anasayfa taranmadıysa derinlik bilinmez, cezalandırılmaz
    assert sc.reviews_status(0, None, False) == "dikkat" and sc.reviews_status(4, 4.5, False) == "iyi"
    assert sc.reviews_status(4, 2.5, False) == "dikkat" and sc.reviews_status(4, 4.5, True) == "dikkat"
    assert sc.speed_status(95, ["good"]) == "iyi" and sc.speed_status(95, ["ni"]) == "dikkat"
    assert sc.speed_status(40, []) == "sorun" and sc.speed_status(95, ["poor"]) == "sorun"
    assert sc.speed_status(None, []) == "iyi"


def test_geo_book_matching_uses_cleaned_name():
    key = sc.book_key("<b>Kayıp Zamanın İzinde</b> (Ciltli)")
    assert "ciltli" not in key and "<b>" not in key
    assert sc.books_mention(["Kayıp Zamanın İzinde"], key)
    assert not sc.books_mention(["Başka Kitap"], key) and not sc.books_mention([], key) and not sc.books_mention(["x"], "")


def test_number_formatting_is_turkish():
    assert sc.num(12345) == "12.345" and sc.num(3.5, 1) == "3,5" and sc.num(1234.5, 1) == "1.234,5"
    assert sc.pct(0.1234) == "%12,3" and sc.pct(None) is None and sc.num(None) is None
    assert sc.yesno(True) == "Var" and sc.yesno(False) == "Yok" and sc.yesno(None) is None
