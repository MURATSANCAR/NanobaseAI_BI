"""2026-09-24/25, müşteri VM'i (K5): "2026 şuabt ayında toplamkaç adet satış gerçekleşmiştir", "son 3 ayda aylık kesilen
satış ve iade faturalarının saysıı ve toplam tutatrları nedir" — birkaç harf yüzünden "katalogda tanımlı değil" reddi.
Yalnız çözülemeyen kelime, yalnız tek adaylı ve yalnız daha çok şey çözüyorsa düzeltilir."""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import Mapping, SemanticType
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.spelling import Speller, distance
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 27)


def test_distance_counts_a_swap_as_one():
    assert distance("suabt", "subat") == 1
    assert distance("tutatr", "tutar") == 1
    assert distance("kitap", "kupon") > 1


def test_speller_splits_glued_words_and_fixes_one_letter_but_never_guesses_between_two():
    sp = Speller(["subat", "tutar", "sayi", "fatur", "toplam", "satis"])
    assert sp.correct("şuabt") == "subat"
    assert sp.correct("tutatrları") == "tutarlari"
    assert sp.correct("toplamkaç") == "toplam kac"
    assert sp.correct("tutar") is None                       # known: nothing to correct
    sp = Speller(["say", "sayf", "sayi", "tutar"], ["sayisi", "tutari", "nedir"])
    assert sp.correct("saysıı") == "sayisi"                   # short root, two neighbours: the written word decides
    assert sp.correct("tutarınedir") == "tutari nedir"
    assert Speller(["kalem", "kalen"]).correct("kalex") is None   # two candidates: no guess


def test_a_misspelt_month_is_read_and_the_reading_is_said(catalog, profiles):
    _certify(catalog, "satış tutarı", SemanticType.METRIC, Mapping(concept_id="", entity="INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
             formula="SUM(INVOICE.NETTOTAL)"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("2026 şuabt ayında satış tutarı", today=TODAY)
    assert [(t.start, t.end) for t in sq.temporal] == [(date(2026, 2, 1), date(2026, 3, 1))], sq.temporal
    assert not sq.unresolved, sq.unresolved
    assert any("şuabt" in e and "subat" in e for e in sq.explanation), sq.explanation
    assert sq.question == "2026 şuabt ayında satış tutarı"
