"""Kolon başlığındaki ASCII sözcükler katalogdaki Türkçe yazımla yazılır («Satis tutari» → «Satış tutarı»)."""
from semantic_bridge.display_words import build


def test_ascii_words_get_the_catalog_spelling():
    words = build(["net satış tutarı", "satış adedi", "geçen yıl", "Satış", "satis tutari", "İade tutarı"])
    assert words["satis"] == "satış"
    assert words["tutari"] == "tutarı"
    assert words["gecen"] == "geçen" and words["yil"] == "yıl"
    assert "net" not in words and "iade" not in words  # zaten ASCII yazılan sözcük haritaya girmez


def test_most_frequent_spelling_wins_and_ascii_terms_do_not_vote():
    assert build(["kâr marjı", "kâr", "kar payı", "kar"])["kar"] == "kâr"
