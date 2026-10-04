"""SEO → CRM kitap kartı yazımı: saf kurallar (alan listesi, uzunluk, alt metin, SQL). Ağ ve veritabanı yok."""
from datetime import datetime, timezone

import pytest

from semantic_bridge.seo_geo import crm_write as w

STAMP = datetime(2026, 10, 4, 9, 30, 15, 123, tzinfo=timezone.utc)


def test_alt_text_adds_author_and_respects_length():
    assert w.alt_text("Bitki Sevenler Kulübü", "Nick Arnold") == "Bitki Sevenler Kulübü – Nick Arnold kitap kapağı"
    assert w.alt_text("Nick Arnold Seçkisi", "Nick Arnold") == "Nick Arnold Seçkisi kitap kapağı"
    assert w.alt_text("", "X") == ""
    long = w.alt_text("Uzun " * 60, "Yazar")
    assert len(long) <= w.FIELDS["new_kapakalt"] and long.endswith(" kitap kapağı")


def test_build_maps_only_invisible_fields_and_skips_empty():
    f = w.build({"ProductName": "Kitap", "Model": "Yazar"},
                {"SeoTitle": "Kitap - Yazar | Timaş", "SeoDescription": "", "Details": "<p>sayfada görünür</p>",
                 "SearchKeywords": "a,b"}, STAMP)
    assert set(f) == {"new_seobaslik", "new_kapakalt", "new_seodurum", "new_seoguncelleme"}
    assert f["new_seodurum"] == w.DURUM_ONAYLANDI
    assert f["new_seoguncelleme"] == datetime(2026, 10, 4, 9, 30, 15)
    assert w.build({}, {}, STAMP) == {}


def test_build_cuts_to_crm_length():
    f = w.build({}, {"SeoDescription": "kelime " * 80}, STAMP)
    assert len(f["new_seoaciklama"]) <= 300


def test_check_rejects_unlisted_and_too_long():
    w.check({"new_seobaslik": "x", "new_seodurum": 2, "new_seoguncelleme": STAMP})
    with pytest.raises(ValueError):
        w.check({"new_ozet": "arka kapak"})
    with pytest.raises(ValueError):
        w.check({"new_seobaslik": "x" * 101})


def test_sql_only_listed_columns_and_modifiedon():
    sql = w.update_sql("Timas_MSCRM.dbo.", ["new_seobaslik", "new_seodurum"])
    assert sql.startswith("UPDATE Timas_MSCRM.dbo.new_kitapBase SET new_seobaslik = ?, new_seodurum = ?, ModifiedOn = GETUTCDATE()")
    assert sql.endswith("WHERE new_kitapId = ? AND statecode = 0")
    with pytest.raises(ValueError):
        w.update_sql("dbo.", ["new_seobaslik", "new_ozet"])
    with pytest.raises(ValueError):
        w.update_sql("dbo.", [])
    assert "new_kapakalt" in w.select_sql("dbo.")


def test_same_compares_text_fields_only():
    f = {"new_seobaslik": "A", "new_seodurum": 2}
    assert w.same(f, {"new_seobaslik": " A ", "new_seodurum": None})
    assert not w.same(f, {"new_seobaslik": None})
